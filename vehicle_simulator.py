"""
무인택시 차량 시뮬레이터
- N대 동시 asyncio 실행
- MQTT로 telemetry 3초마다 publish
- DISPATCH 명령 수신 시 경로 좌표 따라 이동
- 연결 끊김 시 버퍼에 적재 → 재연결 후 flush
- 센서 소모 시뮬레이션 + 임계값 alerts 자동 추가
"""

import argparse
import asyncio
import math
import random
import sys
from datetime import datetime, timezone

# --mode local → config_local.py
# --mode aws   → config_aws.py (기본값)
_parser = argparse.ArgumentParser()
_parser.add_argument('--mode', choices=['local', 'aws'], default='aws',
                     help='local: Mosquitto / aws: AWS IoT Core')
_args, _ = _parser.parse_known_args()

if _args.mode == 'local':
    import config_local as _cfg
    print("[설정] 로컬 Mosquitto 모드")
else:
    import config_aws as _cfg
    print("[설정] AWS IoT Core 모드")

sys.modules['config'] = _cfg

from mqtt_client import VehicleMqttClient
from location_buffer import LocationBuffer
from config import (
    TELEMETRY_INTERVAL, SIM_SPEED, SIM_VEHICLE_SPEED, TAXI_STAND_POSITIONS,
    BATTERY_DRAIN_PER_TICK,
    ENGINE_OIL_DRAIN_PER_TICK, BRAKE_OIL_DRAIN_PER_TICK,
    WASHER_FLUID_DRAIN_PER_TICK, TIRE_PRESSURE_DRAIN_PER_TICK,
    THRESHOLD
)


class Vehicle:

    def __init__(self, vehicle_id: int, initial_pos: dict):
        self.vehicle_id    = vehicle_id
        self.latitude      = initial_pos["lat"]
        self.longitude     = initial_pos["lng"]
        self.speed         = 0
        self.heading       = 0.0
        self.status        = "idle"
        self.autonomy_mode = "auto"
        self.trip_id       = None
        self.seq           = 0
        self.speed_mps     = SIM_VEHICLE_SPEED / 3.6  # 기본값, DISPATCH 시 덮어씀

        # 센서 초기값 (차량마다 랜덤)
        self.battery       = random.randint(60, 100)
        self.tire_pressure = {
            "front_left":  random.randint(33, 38),
            "front_right": random.randint(33, 38),
            "rear_left":   random.randint(33, 38),
            "rear_right":  random.randint(33, 38),
        }
        self.engine_oil    = random.randint(50, 100)
        self.brake_oil     = random.randint(50, 100)
        self.washer_fluid  = random.randint(30, 100)
        self.ext_temp      = round(random.uniform(10.0, 30.0), 1)

        # 이미 events 전송한 코드 추적 (중복 전송 방지)
        self._alerted = set()

        # 경로 관련
        self.route        = []
        self.route_index  = 0

        # MQTT / 버퍼
        self.mqtt   = VehicleMqttClient(str(vehicle_id))
        self.buffer = LocationBuffer(str(vehicle_id))

        self.mqtt.on_command      = self._handle_command
        self.mqtt.on_connected    = self._on_connected
        self.mqtt.on_disconnected = self._on_disconnected

    # ----------------------------------------------------------------
    # 메인 루프
    # ----------------------------------------------------------------
    async def run(self):
        self.mqtt.connect()

        # 연결 대기 (최대 10초)
        for _ in range(20):
            if self.mqtt.is_connected:
                break
            await asyncio.sleep(0.5)

        if not self.mqtt.is_connected:
            print(f"[taxi_{self.vehicle_id:03d}] 연결 실패 — 재시도 대기 중")
        # snapshot은 _on_connected 콜백에서 전송 (연결 보장)

        while True:
            await asyncio.sleep(TELEMETRY_INTERVAL / SIM_SPEED)

            self._drain_sensors()
            alerts   = self._check_thresholds()
            telemetry = self._build_telemetry(alerts)

            if self.mqtt.is_connected:
                self.mqtt.publish_telemetry(telemetry)
                print(f"[taxi_{self.vehicle_id:03d}] "
                      f"lat={self.latitude:.5f} lng={self.longitude:.5f} "
                      f"spd={self.speed} bat={self.battery}% "
                      f"status={self.status} seq={self.seq}"
                      + (f" ALERTS={list(alerts.keys())}" if alerts else ""))
            else:
                self.buffer.add(telemetry)
                print(f"[taxi_{self.vehicle_id:03d}] 버퍼 적재 ({self.buffer.size()}개)")

            if self.status != "idle":
                self._move()

    # ----------------------------------------------------------------
    # 센서 소모 (주행 중에만)
    # ----------------------------------------------------------------
    def _drain_sensors(self):
        if self.status == "idle":
            return

        self.battery      = round(max(0, self.battery      - BATTERY_DRAIN_PER_TICK),      2)
        self.engine_oil   = round(max(0, self.engine_oil   - ENGINE_OIL_DRAIN_PER_TICK),   2)
        self.brake_oil    = round(max(0, self.brake_oil    - BRAKE_OIL_DRAIN_PER_TICK),    2)
        self.washer_fluid = round(max(0, self.washer_fluid - WASHER_FLUID_DRAIN_PER_TICK), 2)

        # 타이어 공기압 소모
        for pos in self.tire_pressure:
            self.tire_pressure[pos] = round(
                max(0, self.tire_pressure[pos] - TIRE_PRESSURE_DRAIN_PER_TICK), 2
            )

    # ----------------------------------------------------------------
    # 임계값 체크 → alerts dict 반환, 최초 이탈 시 events 전송
    # ----------------------------------------------------------------
    def _check_thresholds(self) -> dict:
        alerts = {}

        # 단순 수치 체크
        simple_checks = [
            ("battery",      self.battery,      THRESHOLD["battery"]),
            ("engine_oil",   self.engine_oil,    THRESHOLD["engine_oil"]),
            ("brake_oil",    self.brake_oil,     THRESHOLD["brake_oil"]),
            ("washer_fluid", self.washer_fluid,  THRESHOLD["washer_fluid"]),
        ]
        for code, value, threshold in simple_checks:
            if value <= threshold:
                alerts[code] = round(value, 1)
                if code not in self._alerted:
                    self._alerted.add(code)
                    self.mqtt.publish_event(
                        f"{code.upper()}_LOW",
                        {"value": round(value, 1), "threshold": threshold}
                    )
                    print(f"[taxi_{self.vehicle_id:03d}] EVENT: {code.upper()}_LOW = {value}")
            else:
                self._alerted.discard(code)

        # 타이어: 각 위치별로 체크 (어떤 타이어인지 포함)
        low_tires = {
            pos: psi
            for pos, psi in self.tire_pressure.items()
            if psi <= THRESHOLD["tire_pressure"]
        }
        if low_tires:
            alerts["tire_pressure"] = low_tires
            if "tire_pressure" not in self._alerted:
                self._alerted.add("tire_pressure")
                self.mqtt.publish_event(
                    "TIRE_PRESSURE_LOW",
                    {"tires": low_tires, "threshold": THRESHOLD["tire_pressure"]}
                )
                print(f"[taxi_{self.vehicle_id:03d}] EVENT: TIRE_PRESSURE_LOW = {low_tires}")
        else:
            self._alerted.discard("tire_pressure")

        # 외부 온도
        temp_alert = (self.ext_temp < THRESHOLD["ext_temp_min"] or
                      self.ext_temp > THRESHOLD["ext_temp_max"])
        if temp_alert:
            alerts["ext_temp"] = self.ext_temp
            if "ext_temp" not in self._alerted:
                self._alerted.add("ext_temp")
                self.mqtt.publish_event(
                    "EXT_TEMP_OUT_OF_RANGE",
                    {"value": self.ext_temp,
                     "min": THRESHOLD["ext_temp_min"],
                     "max": THRESHOLD["ext_temp_max"]}
                )
                print(f"[taxi_{self.vehicle_id:03d}] EVENT: EXT_TEMP_OUT_OF_RANGE = {self.ext_temp}")
        else:
            self._alerted.discard("ext_temp")

        return alerts

    # ----------------------------------------------------------------
    # 이동 처리 — 속력 기반 보간 이동
    # ----------------------------------------------------------------
    def _move(self):
        if not self.route or self.route_index >= len(self.route):
            self._on_arrived()
            return

        # 이번 tick에 이동 가능한 거리 (m)
        # DISPATCH 시 전달받은 평균 속도 사용 (카카오 거리/시간 기반)
        remaining_m = self.speed_mps * TELEMETRY_INTERVAL

        prev_lat, prev_lng = self.latitude, self.longitude

        while remaining_m > 0.5 and self.route_index < len(self.route):
            target = self.route[self.route_index]
            dist_to_wp = self._haversine(
                self.latitude, self.longitude, target["lat"], target["lng"]
            )

            if dist_to_wp <= remaining_m:
                self.latitude  = target["lat"]
                self.longitude = target["lng"]
                remaining_m   -= dist_to_wp
                self.route_index += 1
            else:
                # 웨이포인트까지 못 가고 중간에서 멈춤 — 선형 보간
                ratio = remaining_m / dist_to_wp
                self.latitude  += (target["lat"]  - self.latitude)  * ratio
                self.longitude += (target["lng"] - self.longitude) * ratio
                remaining_m = 0

        # 실제 이동 거리로 speed / heading 계산
        moved_m = self._haversine(prev_lat, prev_lng, self.latitude, self.longitude)
        self.speed   = int(min((moved_m / TELEMETRY_INTERVAL) * 3.6, 120))
        self.heading = self._calc_heading(prev_lat, prev_lng, self.latitude, self.longitude)

        if self.route_index >= len(self.route):
            self._on_arrived()

    def _on_arrived(self):
        print(f"[taxi_{self.vehicle_id:03d}] 목적지 도착 — trip_id={self.trip_id}")
        self.mqtt.publish_arrived(self.trip_id)
        self.status      = "idle"
        self.trip_id     = None
        self.route       = []
        self.route_index = 0
        self.speed       = 0

    # ----------------------------------------------------------------
    # MQTT 명령 처리
    # ----------------------------------------------------------------
    def _handle_command(self, payload: dict):
        cmd_type = payload.get("type")

        if cmd_type == "DISPATCH":
            # 이미 운행 중이면 현재 trip 완료 처리 후 수락
            if self.status != "idle":
                print(f"[taxi_{self.vehicle_id:03d}] 운행 중 DISPATCH 무시 "
                      f"(status={self.status})")
                return

            self.trip_id       = payload["trip_id"]
            self.route         = payload["route"]
            self.route_index   = 0
            # phase: "to_pickup"(1차, 차→출발지) | "to_dest"(2차, 출발지→목적지)
            phase = payload.get("phase", "to_pickup")
            self.status        = "moving_to_pickup" if phase == "to_pickup" else "driving"
            self.autonomy_mode = "auto"
            # 서버가 준 거리/예상시간으로 차량이 직접 평균 속도 계산
            distance_m = payload.get("distance_m")
            duration_s = payload.get("duration_s")
            if distance_m and duration_s and duration_s > 0:
                self.speed_mps = distance_m / duration_s
            print(f"[taxi_{self.vehicle_id:03d}] 배차 수신 ({phase}) — "
                  f"trip={self.trip_id} 경로 {len(self.route)}개 좌표 "
                  f"평균속도={self.speed_mps*3.6:.1f}km/h")
            self.mqtt.publish_ack(self.trip_id, "DISPATCH")

        elif cmd_type == "REROUTE":
            self.route       = payload["route"]
            self.route_index = 0
            print(f"[taxi_{self.vehicle_id:03d}] 재경로 수신 — "
                  f"{len(self.route)}개 좌표")
            self.mqtt.publish_ack(self.trip_id or "", "REROUTE")

        elif cmd_type == "EMERGENCY_STOP":
            print(f"[taxi_{self.vehicle_id:03d}] 긴급 정지 명령 수신")
            self.status        = "idle"
            self.speed         = 0
            self.autonomy_mode = "manual"
            self.mqtt.publish_ack(payload.get("trip_id", ""), "EMERGENCY_STOP")

    # ----------------------------------------------------------------
    # 연결 상태 콜백
    # ----------------------------------------------------------------
    def _on_connected(self):
        # 연결 완료 시 snapshot 전송 (최초 연결 + 재연결 모두)
        self._publish_snapshot()

        # 재연결 시 버퍼 flush
        if not self.buffer.is_empty():
            buffered = self.buffer.flush()
            self.mqtt.publish_buffered(buffered)
            print(f"[taxi_{self.vehicle_id:03d}] 버퍼 flush — {len(buffered)}개 전송")

    def _on_disconnected(self):
        print(f"[taxi_{self.vehicle_id:03d}] 연결 끊김 — 버퍼 모드 시작")

    # ----------------------------------------------------------------
    # telemetry / snapshot 빌드
    # ----------------------------------------------------------------
    def _build_telemetry(self, alerts: dict) -> dict:
        self.seq += 1
        payload = {
            "seq":           self.seq,
            "vehicle_id":    self.vehicle_id,
            "latitude":      self.latitude,
            "longitude":     self.longitude,
            "speed":         self.speed,
            "heading":       self.heading,
            "battery":       self.battery,
            "autonomy_mode": self.autonomy_mode,
            "status":        self.status,
            "timestamp":     _now_iso()
        }
        if self.trip_id is not None:
            payload["trip_id"] = self.trip_id
        if alerts:
            payload["alerts"] = alerts
        return payload

    def _publish_snapshot(self):
        snapshot = {
            "vehicle_id":    self.vehicle_id,
            "battery":       self.battery,
            "tire_pressure": self.tire_pressure,
            "engine_oil":    self.engine_oil,
            "brake_oil":     self.brake_oil,
            "washer_fluid":  self.washer_fluid,
            "ext_temp":      self.ext_temp,
            "timestamp":     _now_iso()
        }
        self.mqtt.publish_snapshot(snapshot)
        print(f"[taxi_{self.vehicle_id:03d}] snapshot 전송")

    # ----------------------------------------------------------------
    # 계산 헬퍼
    # ----------------------------------------------------------------
    def _calc_heading(self, lat1, lng1, lat2, lng2) -> float:
        d_lng = math.radians(lng2 - lng1)
        lat1  = math.radians(lat1)
        lat2  = math.radians(lat2)
        x = math.sin(d_lng) * math.cos(lat2)
        y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(d_lng)
        return round((math.degrees(math.atan2(x, y)) + 360) % 360, 1)

    def _haversine(self, lat1, lng1, lat2, lng2) -> float:
        R = 6371000
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        d_phi = math.radians(lat2 - lat1)
        d_lam = math.radians(lng2 - lng1)
        a = math.sin(d_phi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam/2)**2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ----------------------------------------------------------------
# 유틸
# ----------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ================================================================
# 진입점
# ================================================================
async def main():
    vehicle_count = 10
    vehicles = [
        Vehicle(1001 + i, TAXI_STAND_POSITIONS[i % len(TAXI_STAND_POSITIONS)])
        for i in range(vehicle_count)
    ]
    print(f"차량 {vehicle_count}대 시뮬레이터 시작")
    await asyncio.gather(*[v.run() for v in vehicles])


if __name__ == "__main__":
    asyncio.run(main())
