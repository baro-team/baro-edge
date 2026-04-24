# Edge 설계도 — 차량 데이터 송신 전략

---

## 1. 데이터 분류

| 필드 | 타입 | 전송 방식 | 이유 |
|------|------|-----------|------|
| `vehicle_id` | bigint | 모든 메시지 포함 | 차량 식별자 |
| `seq` | int | 모든 telemetry | 순서 보장 확인용 |
| `trip_id` | string | 모든 telemetry | 운행 식별자 |
| `latitude` | float | 실시간 (3초) | 위치는 계속 변함 |
| `longitude` | float | 실시간 (3초) | 위치는 계속 변함 |
| `speed` | int (km/h) | 실시간 (3초) | 실제 이동 거리 기반 계산 |
| `heading` | float (°) | 실시간 (3초) | 방위각 (0°=북, 시계방향) |
| `battery` | int (%) | 실시간 (3초) | 배차 가능 여부 판단 (전기차) |
| `autonomy_mode` | string | 실시간 (3초) | auto / manual |
| `status` | string | 실시간 (3초) | idle / moving_to_pickup / driving |
| `timestamp` | timestamp | 모든 메시지 포함 | 데이터 시간 기준 |
| `tire_pressure` | int (psi) | 조건부 | 정상 시 불필요, 이상 시 추가 |
| `engine_oil` | int (%) | 조건부 | 정상 시 불필요, 이상 시 추가 |
| `brake_oil` | int (%) | 조건부 | 정상 시 불필요, 이상 시 추가 |
| `washer_fluid` | int (%) | 조건부 | 정상 시 불필요, 이상 시 추가 |
| `ext_temp` | float (°C) | 조건부 | 극한 온도 시에만 추가 |

---

## 2. MQTT 토픽 구조

### 2-1. telemetry — 실시간 (3초마다, QoS 0)

```
토픽: vehicles/{vehicle_id}/telemetry
```

**정상 상태 payload (기본형):**
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

**이상 감지 시 payload (확장형):**

차량이 임계값 이하로 판단하면 `alerts` 필드를 추가하여 전송.
이상이 해소될 때까지 매 3초마다 포함.

```json
{
    "seq": 1043,
    "vehicle_id": 1001,
    "trip_id": "trip_abc123",
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
        "engine_oil": 12,
        "brake_oil": 18,
        "washer_fluid": 8,
        "ext_temp": -15.2
    }
}
```

---

### 2-2. snapshot — 연결 시마다 1회 (QoS 1)

```
토픽: vehicles/{vehicle_id}/snapshot
```

최초 연결 및 재연결 시마다 1회 전송. 서버가 차량 전체 상태를 파악하기 위한 점검 데이터.

```json
{
    "vehicle_id": 1001,
    "battery": 82,
    "tire_pressure": {
        "front_left": 36,
        "front_right": 36,
        "rear_left": 35,
        "rear_right": 36
    },
    "engine_oil": 74,
    "brake_oil": 80,
    "washer_fluid": 60,
    "ext_temp": 18.5,
    "timestamp": "2026-04-22T09:00:00Z"
}
```

---

### 2-3. events — 이상 발생 / 도착 시 1회 (QoS 1)

```
토픽: vehicles/{vehicle_id}/events
```

**경고 이벤트** — 임계값 진입 시점에 1회 전송. 이후로는 telemetry alerts 필드에 포함.

```json
{
    "vehicle_id": 1001,
    "event_type": "WARNING",
    "code": "TIRE_PRESSURE_LOW",
    "detail": { "tires": { "front_left": 27 }, "threshold": 28 },
    "timestamp": "2026-04-22T09:00:00Z"
}
```

**도착 이벤트** — 목적지 도달 시 1회 전송.

```json
{
    "vehicle_id": 1001,
    "event_type": "ARRIVED",
    "trip_id": "trip_abc123",
    "timestamp": "2026-04-22T09:00:00Z"
}
```

---

### 2-4. ack — 명령 수신 확인 (QoS 1)

```
토픽: vehicles/{vehicle_id}/ack
```

```json
{
    "vehicle_id": 1001,
    "command_type": "DISPATCH",
    "trip_id": "trip_abc123",
    "timestamp": "2026-04-22T09:00:00Z"
}
```

---

### 2-5. commands — 서버 → 차량 (QoS 1)

```
토픽: vehicles/{vehicle_id}/commands
```

**DISPATCH** — 배차 명령. 카카오 Directions API 경로 좌표 + 거리/예상시간 포함.

```json
{
    "type": "DISPATCH",
    "trip_id": "trip_abc123",
    "route": [
        { "lat": 37.5665, "lng": 126.9780 },
        { "lat": 37.5700, "lng": 126.9850 }
    ],
    "pickup_index": 10,
    "distance_m": 8500,
    "duration_s": 1200
}
```

- `pickup_index` : 해당 인덱스 웨이포인트 도달 시 status → `driving`
- `distance_m` : 카카오 Directions API 응답의 총 거리 (m)
- `duration_s` : 카카오 Directions API 응답의 예상 소요시간 (초)
- 차량이 `distance_m / duration_s` 로 평균 속도를 직접 계산하여 이동

**REROUTE** — 경로 재설정.

```json
{
    "type": "REROUTE",
    "route": [ ... ],
    "pickup_index": 0
}
```

**EMERGENCY_STOP** — 긴급 정지. autonomy_mode → `manual`.

```json
{
    "type": "EMERGENCY_STOP",
    "trip_id": "trip_abc123"
}
```

---

## 3. 조건부 전송 임계값

| 항목 | 정상 범위 | 임계값 (이상 감지) | 서버 처리 |
|------|----------|-------------------|-----------|
| `battery` | 20% 이상 | 20% 이하 | 충전소 복귀 명령 |
| `tire_pressure` | 30~40 psi | 28 psi 이하 | 배차 거부 + 정비 명령 |
| `engine_oil` | 25% 이상 | 25% 이하 | 배차 거부 + 정비 명령 |
| `brake_oil` | 30% 이상 | 30% 이하 | 즉시 운행 중단 |
| `washer_fluid` | 10% 이상 | 10% 이하 | 알림만 (운행 유지) |
| `ext_temp` | -10°C ~ 45°C | 범위 초과 | 속도 제한 명령 |

---

## 4. 차량 이동 로직

```
DISPATCH 수신
    │
    ├─ route      = [{lat, lng}, ...] 카카오 Directions API 경로 좌표
    ├─ distance_m = 카카오 총 거리 (m)
    ├─ duration_s = 카카오 예상 소요시간 (초)
    │
    ├─ [차량 자체 계산] speed_mps = distance_m / duration_s
    │
    └─ 매 tick(TELEMETRY_INTERVAL초)마다 _move() 호출
            │
            ├─ tick당 이동 가능 거리 계산
            │     remaining_m = speed_mps × TELEMETRY_INTERVAL
            │
            └─ 웨이포인트 순서대로 선형 보간 이동
                    │
                    ├─ dist_to_wp ≤ remaining_m
                    │       → 웨이포인트 도달 후 다음으로 연속 진행
                    │       → route_index > pickup_index 이면 status = "driving"
                    │
                    └─ dist_to_wp > remaining_m
                            → 방향 유지하며 remaining_m만큼만 이동
                            → 다음 tick에 이어서 진행
```

- `speed` : 실제 이동 거리(m) / TELEMETRY_INTERVAL × 3.6 (km/h)
- `heading` : 이전 위치 → 현재 위치 방위각 (0°=북, 시계방향)
- `SIM_SPEED` : sleep 주기만 줄임 (이동 거리와 무관)

---

## 5. 차량 내부 판단 로직

```
[차량 내부 센서 모니터링] (주행 중에만 소모)
        │
        ├─ 정상 범위 내
        │       └─→ telemetry 기본형 전송 (3초마다)
        │
        └─ 임계값 이하 감지
                ├─→ events 토픽에 이상 1회 전송 (QoS 1)
                └─→ 이후 telemetry에 alerts 필드 추가
                        (이상 해소될 때까지 계속 포함)
```

---

## 6. 서버 수신 처리 방향

```
telemetry 수신
    │
    ├─ alerts 필드 없음   → Redis 위치 업데이트
    │
    └─ alerts 필드 있음   → Redis 위치 업데이트
                          → 차량 상태 이상 플래그 설정
                          → 해당 차량 배차 제외
                          → 관제 알림

snapshot 수신
    │
    └─ 전체 상태 검증
         → 이상 항목 있으면 배차 거부
         → 전체 정상이면 배차 가능 상태로 등록

events 수신
    │
    ├─ WARNING
    │    brake_oil 이상 → 즉시 운행 중단 명령
    │    나머지 → 배차 제외 + 관제 알림
    │
    └─ ARRIVED → 다음 배차 처리 (출발지→목적지 2차 DISPATCH)
```

---

## 7. 데이터 흐름 요약

```
차량 센서
    │
    ├─ 위치/속도/배터리/연료   →  telemetry (3초, QoS 0)
    │
    ├─ 연결/재연결 시 전체 상태 →  snapshot (1회, QoS 1)
    │
    ├─ 임계값 최초 감지         →  events WARNING (1회, QoS 1)
    │                               + 이후 telemetry alerts에 포함
    │
    ├─ 목적지 도달              →  events ARRIVED (1회, QoS 1)
    │
    └─ 명령 수신 확인           →  ack (QoS 1)

서버 → 차량
    │
    ├─ DISPATCH      (카카오 경로 + 평균 속도, QoS 1)
    ├─ REROUTE       (새 경로, QoS 1)
    └─ EMERGENCY_STOP (즉시 정지, QoS 1)
```

---

*작성일: 2026-04-22*
