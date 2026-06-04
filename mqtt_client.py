"""
AWS IoT Core / Mosquitto MQTT 클라이언트 — aiomqtt 기반 asyncio 네이티브
- 백그라운드 스레드 없음: GIL 경쟁 · keepalive deadline miss 제거
- publish: fire-and-forget (asyncio.create_task)
- 재연결: Vehicle.run() 의 reconnect loop 에서 관리
"""

import asyncio
import json
import ssl
from contextlib import asynccontextmanager
from typing import Optional, Callable

import aiomqtt
from config import MQTT_BROKER_HOST, MQTT_BROKER_PORT


def _build_tls_context() -> Optional[ssl.SSLContext]:
    if MQTT_BROKER_PORT != 8883:
        return None
    try:
        from config import CERT_PATH, KEY_PATH, CA_PATH
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.load_verify_locations(CA_PATH)
        ctx.load_cert_chain(CERT_PATH, KEY_PATH)
        return ctx
    except ImportError:
        print("[MQTT] 경고: 8883 포트인데 인증서 설정 없음")
        return None


class VehicleMqttClient:

    def __init__(self, vehicle_id: str):
        self.vehicle_id   = vehicle_id
        self.is_connected = False
        self._client: Optional[aiomqtt.Client] = None

        self.on_command:      Optional[Callable] = None
        self.on_connected:    Optional[Callable] = None
        self.on_disconnected: Optional[Callable] = None

    # ----------------------------------------------------------------
    # Publish (동기 인터페이스 — 내부에서 asyncio.create_task 사용)
    # vehicle_simulator.py 코드 변경 최소화
    # ----------------------------------------------------------------
    def publish_telemetry(self, payload: dict):
        self._fire(f"vehicles/{self.vehicle_id}/telemetry", payload, qos=0)

    def publish_buffered(self, buffered_list: list):
        self._fire(f"vehicles/{self.vehicle_id}/telemetry/buffered", {
            "vehicle_id": self.vehicle_id,
            "buffered":   buffered_list,
        }, qos=1)

    def publish_ack(self, trip_id: str, command_type: str = "DISPATCH"):
        self._fire(f"vehicles/{self.vehicle_id}/ack", {
            "vehicle_id":   self.vehicle_id,
            "command_type": command_type,
            "trip_id":      trip_id,
        }, qos=1)

    def publish_snapshot(self, snapshot: dict):
        self._fire(f"vehicles/{self.vehicle_id}/snapshot", snapshot, qos=1)

    def publish_event(self, event_code: str, detail: dict = None):
        self._fire(f"vehicles/{self.vehicle_id}/events", {
            "vehicle_id": self.vehicle_id,
            "event_type": "WARNING",
            "code":       event_code,
            "detail":     detail or {},
        }, qos=1)

    def publish_arrived(self, trip_id: str):
        self._fire(f"vehicles/{self.vehicle_id}/events", {
            "vehicle_id": self.vehicle_id,
            "event_type": "ARRIVED",
            "trip_id":    trip_id,
        }, qos=1)

    def _fire(self, topic: str, payload: dict, qos: int):
        if not self.is_connected or self._client is None:
            return
        asyncio.create_task(self._do_publish(topic, payload, qos))

    async def _do_publish(self, topic: str, payload: dict, qos: int):
        if not self.is_connected or self._client is None:
            return
        try:
            await self._client.publish(topic, json.dumps(payload), qos=qos)
        except aiomqtt.MqttError:
            pass

    # ----------------------------------------------------------------
    # 메시지 수신 루프
    # ----------------------------------------------------------------
    async def _listen(self):
        try:
            async for message in self._client.messages:
                try:
                    payload = json.loads(message.payload.decode())
                    if "/commands" in str(message.topic):
                        print(f"[{self.vehicle_id}] 명령 수신: {payload.get('type')}")
                        if self.on_command:
                            self.on_command(payload)
                except Exception as e:
                    print(f"[{self.vehicle_id}] 메시지 파싱 오류: {e}")
        except Exception as e:
            print(f"[{self.vehicle_id}] 수신 루프 비정상 종료: {e}")
            raise

    # ----------------------------------------------------------------
    # 연결 컨텍스트 매니저 (Vehicle.run() 에서 사용)
    # ----------------------------------------------------------------
    @asynccontextmanager
    async def session(self):
        tls = _build_tls_context()
        kwargs = dict(
            hostname=MQTT_BROKER_HOST,
            port=MQTT_BROKER_PORT,
            identifier=f"vehicle-{self.vehicle_id}",
            keepalive=60,
            clean_session=False,  # persistent session: IoT Core buffers QoS 1 commands while offline
        )
        if tls:
            kwargs["tls_context"] = tls

        async with aiomqtt.Client(**kwargs) as client:
            self._client = client
            self.is_connected = True
            print(f"[{self.vehicle_id}] MQTT 연결 완료")

            await client.subscribe(f"vehicles/{self.vehicle_id}/commands", qos=1)

            if self.on_connected:
                self.on_connected()

            listener = asyncio.create_task(self._listen())
            try:
                yield listener  # caller can monitor listener health
            finally:
                if not listener.done():
                    listener.cancel()
                try:
                    await listener
                except (asyncio.CancelledError, Exception):
                    pass
                self.is_connected = False
                self._client = None
                if self.on_disconnected:
                    self.on_disconnected()
