# baro-edge 주행 시뮬레이터 구조 설명

무인택시 차량을 소프트웨어로 흉내내는 시뮬레이터입니다.  
실제 차량 대신 Python 프로세스가 MQTT로 telemetry를 보내고, 배차 명령을 받아 경로를 따라 이동합니다.

---

## 전체 구조

```
vehicle_simulator.py   ← 차량 상태 관리 + 주행 로직
mqtt_client.py         ← MQTT 연결 / 송수신
location_buffer.py     ← 연결 끊김 시 데이터 임시 보관
config.py              ← 설정값 (시뮬레이션 속도, 임계값, 초기 위치 등)
```

---

## 실행 흐름

```
python vehicle_simulator.py --mode aws
           │
           ▼
차량 10대 동시 생성 (vehicle_id: 1001 ~ 1010)
각 차량은 서울 내 실제 택시 승차대 좌표에서 시작
           │
           ▼
각 차량마다 asyncio Task 생성 → 독립적으로 동작
           │
           ▼
MQTT 연결 → telemetry 3초마다 전송 → 명령 대기
```

> `--mode local`로 실행하면 로컬 Mosquitto 브로커에 연결됩니다 (개발용).

---

## 차량 1대의 동작 사이클

```
[연결]
  └── MQTT 세션 시작 (AWS IoT Core / Mosquitto)
  └── vehicles/{id}/commands 구독
  └── snapshot 전송 (배터리, 타이어 압력, 오일류 초기 상태)
  └── 버퍼에 쌓인 데이터 있으면 일괄 전송 (재연결 시)

[주행 루프 — 3초마다 반복]
  ├── 센서 소모 계산 (주행 중일 때만)
  ├── 임계값 초과 항목 확인 → alerts 포함
  ├── telemetry 전송 (연결 중) 또는 버퍼 적재 (연결 끊김)
  └── 경로 이동 (status가 idle이 아닐 때)

[명령 수신 시 즉시 처리]
  ├── DISPATCH      → 경로 설정, 주행 시작
  ├── REROUTE       → 경로 교체 (진행 중 재경로)
  └── EMERGENCY_STOP → 즉시 정지, 수동 모드 전환

[목적지 도착]
  └── ARRIVED 이벤트 전송 → status = idle
```

---

## MQTT 토픽 구조

| 방향 | 토픽 | 내용 | QoS |
|------|------|------|-----|
| 차량 → 서버 | `vehicles/{id}/telemetry` | 위치, 속도, 배터리 등 | 0 |
| 차량 → 서버 | `vehicles/{id}/telemetry/buffered` | 연결 끊김 중 밀린 데이터 | 1 |
| 차량 → 서버 | `vehicles/{id}/snapshot` | 연결 시 전체 센서 초기 상태 | 1 |
| 차량 → 서버 | `vehicles/{id}/events` | 경고(WARNING), 도착(ARRIVED) | 1 |
| 차량 → 서버 | `vehicles/{id}/ack` | 명령 수신 확인 | 1 |
| 서버 → 차량 | `vehicles/{id}/commands` | DISPATCH, REROUTE, EMERGENCY_STOP | 1 |

---

## 주요 기능 설명

### 1. 경로 이동 (Haversine 기반)

DISPATCH 명령으로 경로 좌표 목록(`route`)을 받으면, 매 tick마다 좌표를 따라 이동합니다.

```
서버가 보내는 DISPATCH 페이로드:
{
  "type": "DISPATCH",
  "trip_id": "trip-001",
  "phase": "to_pickup",         ← "to_pickup"(차→승차지) | "to_dest"(승차지→목적지)
  "route": [{"lat": ..., "lng": ...}, ...],
  "distance_m": 5200,           ← 총 거리 (미터)
  "duration_s": 720             ← 예상 소요 시간 (초)
}
```

- 서버가 준 `distance_m / duration_s`로 차량의 평균 속도를 직접 계산
- Haversine 공식으로 두 좌표 간 실제 거리(미터) 계산
- 웨이포인트를 순서대로 통과하며 선형 보간으로 중간 위치 계산
- heading(방위각)은 이동 전/후 좌표로 계산 (북=0°, 시계 방향)

### 2. 센서 시뮬레이션

주행 중에만 매 tick마다 센서 값이 조금씩 감소합니다.

| 센서 | 감소량(tick당) | 경고 임계값 |
|------|-------------|-----------|
| 배터리 | 0.01% | 20% 이하 |
| 엔진오일 | 0.005% | 25% 이하 |
| 브레이크오일 | 0.003% | 30% 이하 |
| 워셔액 | 0.002% | 10% 이하 |
| 타이어 압력 | 0.002 psi | 28 psi 이하 |

임계값을 처음 넘는 순간 `vehicles/{id}/events`로 경고 이벤트를 전송합니다 (중복 전송 방지).

### 3. 연결 끊김 대응 (오프라인 버퍼)

```
연결 끊김 감지
     │
     ▼
telemetry를 LocationBuffer에 적재 (최대 200개)
     │
     ▼
재연결 성공
     │
     ▼
버퍼 전체를 telemetry/buffered 토픽으로 일괄 전송
```

MQTT 세션은 `clean_session=False`(영구 세션)로 연결합니다.  
덕분에 차량이 잠깐 끊겼을 때 서버가 보낸 QoS 1 명령이 IoT Core에 보관되어, 재연결 시 놓치지 않고 수신합니다.

### 4. 수신 루프 장애 감지

`_listen()` 태스크가 예외로 죽으면 `_telemetry_loop()`에서 감지해 재연결을 트리거합니다.

```python
if listener.done():
    raise MqttError("수신 루프 종료")  → reconnect loop로 올라감
```

### 5. 재연결 백오프

연결 실패 시 재시도 간격이 지수적으로 늘어납니다 (최대 60초).

```
2초 → 4초 → 8초 → 16초 → 32초 → 60초 → 60초 → ...
```

---

## 파일별 역할 요약

| 파일 | 역할 |
|------|------|
| `vehicle_simulator.py` | 차량 상태 머신, 이동 계산, 센서 시뮬레이션, 명령 처리 |
| `mqtt_client.py` | MQTT 연결 수립, 토픽 발행/구독, 수신 루프 관리 |
| `location_buffer.py` | 오프라인 구간 telemetry 임시 저장 및 flush |
| `config.py` / `config_aws.py` / `config_local.py` | 브로커 주소, 인증서 경로, 시뮬레이션 파라미터 |

---

## 실행 방법

```bash
# 로컬 Mosquitto 브로커 (개발)
python vehicle_simulator.py --mode local

# AWS IoT Core (운영)
python vehicle_simulator.py --mode aws
```

`.env` 파일에 IoT Core 접속 정보가 필요합니다:

```
IOT_ENDPOINT=xxxxx.iot.ap-northeast-2.amazonaws.com
IOT_CERT_PATH=certs/xxx-certificate.pem.crt
IOT_KEY_PATH=certs/xxx-private.pem.key
IOT_CA_PATH=certs/AmazonRootCA1.pem
```
