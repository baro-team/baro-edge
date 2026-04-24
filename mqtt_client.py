"""
AWS IoT Core (또는 로컬 Mosquitto) MQTT 클라이언트
- 연결 / 재연결 처리
- telemetry publish
- commands 수신 콜백
"""

import json
import os
import ssl
import paho.mqtt.client as mqtt
from config import MQTT_BROKER_HOST, MQTT_BROKER_PORT


class VehicleMqttClient:

    def __init__(self, vehicle_id: str):
        self.vehicle_id = vehicle_id
        self.is_connected = False

        # 콜백 (vehicle_simulator에서 주입)
        self.on_command = None       # 배차 명령 수신 시
        self.on_connected = None     # 연결 완료 시
        self.on_disconnected = None  # 연결 끊김 시

        self._client = mqtt.Client(client_id=f"vehicle-{vehicle_id}")
        self._client.on_connect    = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message    = self._on_message

    # ----------------------------------------------------------------
    # 연결
    # ----------------------------------------------------------------
    def connect(self):
        # AWS IoT Core (포트 8883) 사용 시 TLS 인증서 자동 적용
        if MQTT_BROKER_PORT == 8883:
            try:
                from config import CERT_PATH, KEY_PATH, CA_PATH
                self._client.tls_set(
                    ca_certs=CA_PATH,
                    certfile=CERT_PATH,
                    keyfile=KEY_PATH,
                    tls_version=ssl.PROTOCOL_TLS_CLIENT
                )
                self._client.tls_insecure_set(False)
            except ImportError:
                print("[MQTT] 경고: 8883 포트인데 인증서 설정이 없습니다")

        self._client.connect_async(MQTT_BROKER_HOST, MQTT_BROKER_PORT, keepalive=10)
        self._client.loop_start()   # 백그라운드 네트워크 루프

    def disconnect(self):
        self._client.loop_stop()
        self._client.disconnect()

    # ----------------------------------------------------------------
    # Publish
    # ----------------------------------------------------------------
    def publish_telemetry(self, payload: dict):
        """실시간 위치/상태 (QoS 0)"""
        topic = f"vehicles/{self.vehicle_id}/telemetry"
        self._publish(topic, payload, qos=0)

    def publish_buffered(self, buffered_list: list):
        """재연결 후 버퍼 flush (QoS 1)"""
        topic = f"vehicles/{self.vehicle_id}/telemetry/buffered"
        payload = {
            "vehicle_id": self.vehicle_id,
            "buffered": buffered_list
        }
        self._publish(topic, payload, qos=1)

    def publish_ack(self, trip_id: str, command_type: str = "DISPATCH"):
        """명령 수신 확인 (QoS 1)"""
        topic = f"vehicles/{self.vehicle_id}/ack"
        payload = {
            "vehicle_id": self.vehicle_id,
            "command_type": command_type,
            "trip_id": trip_id
        }
        self._publish(topic, payload, qos=1)

    def publish_snapshot(self, snapshot: dict):
        """주행 시작 시 차량 전체 상태 1회 전송 (QoS 1)"""
        topic = f"vehicles/{self.vehicle_id}/snapshot"
        self._publish(topic, snapshot, qos=1)

    def publish_event(self, event_code: str, detail: dict = None):
        """경고 이벤트 (QoS 1)"""
        topic = f"vehicles/{self.vehicle_id}/events"
        payload = {
            "vehicle_id": self.vehicle_id,
            "event_type": "WARNING",
            "code": event_code,
            "detail": detail or {}
        }
        self._publish(topic, payload, qos=1)

    def publish_arrived(self, trip_id: str):
        """목적지 도착 이벤트 (QoS 1)"""
        topic = f"vehicles/{self.vehicle_id}/events"
        payload = {
            "vehicle_id": self.vehicle_id,
            "event_type": "ARRIVED",
            "trip_id": trip_id
        }
        self._publish(topic, payload, qos=1)

    # ----------------------------------------------------------------
    # 내부 헬퍼
    # ----------------------------------------------------------------
    def _publish(self, topic: str, payload: dict, qos: int):
        if not self.is_connected:
            return
        self._client.publish(topic, json.dumps(payload), qos=qos)

    # ----------------------------------------------------------------
    # 내부 콜백
    # ----------------------------------------------------------------
    def _on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.is_connected = True
            print(f"[{self.vehicle_id}] MQTT 연결 완료")

            # commands 토픽 구독
            client.subscribe(f"vehicles/{self.vehicle_id}/commands", qos=1)

            if self.on_connected:
                self.on_connected()
        else:
            print(f"[{self.vehicle_id}] MQTT 연결 실패 rc={rc}")

    def _on_disconnect(self, client, userdata, rc):
        self.is_connected = False
        print(f"[{self.vehicle_id}] MQTT 연결 끊김 (rc={rc})")
        if self.on_disconnected:
            self.on_disconnected()

    def _on_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            topic   = msg.topic

            if "/commands" in topic:
                print(f"[{self.vehicle_id}] 명령 수신: {payload.get('type')}")
                if self.on_command:
                    self.on_command(payload)

        except Exception as e:
            print(f"[{self.vehicle_id}] 메시지 파싱 오류: {e}")
