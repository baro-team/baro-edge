# baro-edge — 무인택시 차량 시뮬레이터

무인택시 차량을 시뮬레이션하는 Python 모듈입니다.
실제 차량 대신 MQTT로 telemetry를 AWS IoT Core에 전송하고, 서버로부터 배차 명령을 수신합니다.

---

## 파일 구조

```
baro-edge/
├── vehicle_simulator.py   # 메인 시뮬레이터 (N대 asyncio 동시 실행)
├── mqtt_client.py         # MQTT 연결/발행/수신 (Mosquitto / AWS IoT Core 자동 전환)
├── location_buffer.py     # 연결 끊김 시 telemetry 버퍼
├── config.py              # 설정값 (브로커 주소, 시뮬 속도, 임계값, 승차대 좌표)
├── requirements.txt
├── edge_design.md         # 데이터 송신 전략 설계도
└── certs/                 # AWS IoT Core 인증서 (git 제외)
    ├── baro-vehicle-fleet.cert.pem
    ├── baro-vehicle-fleet.private.key
    └── AmazonRootCA1.pem.txt
```

---

## 설치

```bash
pip install -r requirements.txt
```

---

## 실행

```bash
python vehicle_simulator.py
```

차량 수는 `main()`의 `vehicle_count`로 조정합니다.

```python
vehicle_count = 10  # 10대 실행
```

---

## 브로커 설정

### 로컬 테스트 (Mosquitto)

`config.py`:
```python
MQTT_BROKER_HOST = "localhost"
MQTT_BROKER_PORT = 1883
```

Mosquitto `mosquitto.conf`:
```
listener 1883
protocol mqtt
allow_anonymous true

listener 9001
protocol websockets
allow_anonymous true
```

### AWS IoT Core 연결 (현재 설정)

`config.py`:
```python
MQTT_BROKER_HOST = "a3hgke9tcu6q1e-ats.iot.ap-northeast-2.amazonaws.com"
MQTT_BROKER_PORT = 8883
CERT_PATH = "certs/baro-vehicle-fleet.cert.pem"
KEY_PATH  = "certs/baro-vehicle-fleet.private.key"
CA_PATH   = "certs/AmazonRootCA1.pem.txt"
```

포트 8883 감지 시 TLS 인증서를 자동으로 적용합니다.
로컬 ↔ AWS 전환은 `config.py`에서 포트 번호만 바꾸면 됩니다.

---

## 차량 동작 흐름

```
시작
 │
 ├─ AWS IoT Core MQTT 연결 (TLS)
 ├─ vehicles/{id}/commands 구독
 ├─ snapshot 전송 (전체 센서 상태 1회)
 │
 └─ 대기 (status: idle)
       │
       │  DISPATCH 명령 수신 (phase: to_pickup)
       ▼
 status = "moving_to_pickup"
       │
       │  3초마다 _move() 실행
       │  → speed_mps = distance_m / duration_s (카카오 기반 평균 속도)
       │  → remaining_m = speed_mps × TELEMETRY_INTERVAL (tick당 이동 거리)
       │  → 웨이포인트 선형 보간 이동
       ▼
 목적지(출발지) 도달 → events ARRIVED 전송 → status = "idle"
       │
       │  DISPATCH 명령 수신 (phase: to_dest)
       ▼
 status = "driving"
       │
       │  목적지 도달
       ▼
 events ARRIVED 전송 → status = "idle"
```

---

## MQTT 토픽

### 차량 → 서버 (Publish)

| 토픽 | QoS | 주기 | 내용 |
|------|-----|------|------|
| `vehicles/{id}/telemetry` | 0 | 3초 | 위치, 속도, 배터리, 상태 |
| `vehicles/{id}/telemetry/buffered` | 1 | 재연결 시 | 끊김 구간 버퍼 flush |
| `vehicles/{id}/snapshot` | 1 | 연결/재연결마다 1회 | 전체 센서 상태 |
| `vehicles/{id}/events` | 1 | 이상 감지 / 목적지 도달 시 | WARNING / ARRIVED |
| `vehicles/{id}/ack` | 1 | 명령 수신 시 | 명령 수신 확인 |

### 서버 → 차량 (Subscribe)

| 토픽 | QoS | 명령 종류 |
|------|-----|----------|
| `vehicles/{id}/commands` | 1 | DISPATCH / REROUTE / EMERGENCY_STOP |

---

## DISPATCH 명령 구조

2단계 배차 방식을 사용합니다.

**1차 DISPATCH** — 차량 → 출발지
```json
{
    "type": "DISPATCH",
    "phase": "to_pickup",
    "trip_id": "trip_abc123",
    "route": [
        { "lat": 37.5665, "lng": 126.9780 },
        { "lat": 37.5700, "lng": 126.9850 }
    ],
    "distance_m": 2100,
    "duration_s": 480
}
```

**2차 DISPATCH** — 출발지 → 목적지 (1차 ARRIVED 이벤트 후 서버가 발행)
```json
{
    "type": "DISPATCH",
    "phase": "to_dest",
    "trip_id": "trip_abc123",
    "route": [ ... ],
    "distance_m": 8500,
    "duration_s": 1200
}
```

- `phase: "to_pickup"` → `status = "moving_to_pickup"`
- `phase: "to_dest"` → `status = "driving"` (즉시, 승객 탑승 상태)
- `distance_m / duration_s` → 차량이 직접 평균 속도 계산 (카카오 예상 소요시간 기반)
- `pickup_index` 불필요 — 2단계 배차 구조로 자연스럽게 처리

---

## telemetry payload

### 기본형 (정상 상태)

```json
{
    "seq": 1042,
    "vehicle_id": 1001,
    "trip_id": "trip_abc123",
    "latitude": 37.5665,
    "longitude": 126.9780,
    "speed": 60,
    "heading": 127.5,
    "battery": 78,
    "autonomy_mode": "auto",
    "status": "driving",
    "timestamp": "2026-04-22T09:00:00Z"
}
```

### 확장형 (이상 감지 시 alerts 필드 추가)

```json
{
    "seq": 1043,
    "vehicle_id": 1001,
    "latitude": 37.5665,
    "longitude": 126.9780,
    "speed": 60,
    "heading": 127.5,
    "battery": 78,
    "autonomy_mode": "auto",
    "status": "driving",
    "timestamp": "2026-04-22T09:00:03Z",
    "alerts": {
        "tire_pressure": { "front_left": 27 },
        "brake_oil": 18
    }
}
```

이상이 해소되면 `alerts` 필드가 자동으로 제거됩니다.

---

## 이상 감지 임계값

| 항목 | 임계값 | 최초 감지 시 | 이후 |
|------|--------|-------------|------|
| `battery` | 20% 이하 | events WARNING 1회 전송 | telemetry alerts 포함 |
| `tire_pressure` | 28 psi 이하 | events WARNING 1회 전송 | telemetry alerts 포함 |
| `engine_oil` | 25% 이하 | events WARNING 1회 전송 | telemetry alerts 포함 |
| `brake_oil` | 30% 이하 | events WARNING 1회 전송 | telemetry alerts 포함 |
| `washer_fluid` | 10% 이하 | events WARNING 1회 전송 | telemetry alerts 포함 |
| `ext_temp` | -10°C 미만 / 45°C 초과 | events WARNING 1회 전송 | telemetry alerts 포함 |

---

## 연결 끊김 처리

```
연결 끊김 감지
    │
    └─→ LocationBuffer에 telemetry 적재 (최대 200개)
              │
              └─→ 재연결 성공
                      ├─→ snapshot 전송 (전체 센서 상태)
                      └─→ buffered 토픽으로 버퍼 일괄 flush
```

- 버퍼는 `deque(maxlen=200)` — 초과 시 오래된 데이터부터 자동 삭제
- 재연결은 paho-mqtt `automatic_reconnect=True`로 자동 처리

---

## 시뮬레이션 설정

`config.py`에서 조정합니다.

```python
TELEMETRY_INTERVAL = 3    # telemetry 전송 주기 (초)
SIM_SPEED = 3             # 시뮬레이션 배속 (1=실시간, 3=3배속)
SIM_VEHICLE_SPEED = 60    # 기본 차량 속도 (km/h) — DISPATCH에 distance_m/duration_s 없을 때 사용
BUFFER_MAX_SIZE = 200     # 연결 끊김 시 버퍼 최대 크기

# 센서 소모율 (tick당, 주행 중에만 적용)
BATTERY_DRAIN_PER_TICK       = 0.01   # %
ENGINE_OIL_DRAIN_PER_TICK    = 0.005  # %
BRAKE_OIL_DRAIN_PER_TICK     = 0.003  # %
WASHER_FLUID_DRAIN_PER_TICK  = 0.002  # %
TIRE_PRESSURE_DRAIN_PER_TICK = 0.002  # psi
```

**SIM_SPEED 가이드:**
- `SIM_SPEED = 1` : 실시간 (sleep 3초마다 telemetry 전송)
- `SIM_SPEED = 3` : 3배속 (sleep 1초마다 telemetry 전송)
- `SIM_SPEED = 10` : 10배속, 빠른 테스트용

> SIM_SPEED는 sleep 주기만 줄입니다. 이동 거리(speed_mps × TELEMETRY_INTERVAL)는 변하지 않아 차량 속도에 영향을 주지 않습니다.

---

## 초기 차량 위치

서울 택시 승차대 254개 좌표 기준으로 차량 초기 위치를 배정합니다.
출처: 택시승차대 운영 목록_260223.xlsx

---

## AWS IoT Core 정책

차량 연결에 필요한 IoT 정책 (ap-northeast-2 서울 리전):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "iot:Connect",
      "Resource": "arn:aws:iot:ap-northeast-2:*:client/vehicle-*"
    },
    {
      "Effect": "Allow",
      "Action": "iot:Publish",
      "Resource": "arn:aws:iot:ap-northeast-2:*:topic/vehicles/*"
    },
    {
      "Effect": "Allow",
      "Action": "iot:Subscribe",
      "Resource": "arn:aws:iot:ap-northeast-2:*:topicfilter/vehicles/*"
    },
    {
      "Effect": "Allow",
      "Action": "iot:Receive",
      "Resource": "arn:aws:iot:ap-northeast-2:*:topic/vehicles/*"
    }
  ]
}
```

---

*작성일: 2026-04-23*
