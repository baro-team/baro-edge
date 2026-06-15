# ================================================================
# 로컬 테스트용 설정 (Mosquitto)
# 실행: python vehicle_simulator.py --mode local
# ================================================================

# MQTT - 로컬 Mosquitto
MQTT_BROKER_HOST = "localhost"
MQTT_BROKER_PORT = 1883

TELEMETRY_INTERVAL = 3
SIM_SPEED = 3
SIM_VEHICLE_SPEED = 60
BUFFER_MAX_SIZE = 200

BATTERY_DRAIN_PER_TICK       = 0.01
ENGINE_OIL_DRAIN_PER_TICK    = 0.005
BRAKE_OIL_DRAIN_PER_TICK     = 0.003
WASHER_FLUID_DRAIN_PER_TICK  = 0.002
TIRE_PRESSURE_DRAIN_PER_TICK = 0.002

THRESHOLD = {
    "battery":       20,
    "tire_pressure": 28,
    "engine_oil":    25,
    "brake_oil":     30,
    "washer_fluid":  10,
    "ext_temp_min": -10,
    "ext_temp_max":  45,
}

TAXI_STAND_POSITIONS = [
    # 종로구
    {"lat": 37.5730, "lng": 126.9794},
    # 중구
    {"lat": 37.5636, "lng": 126.9976},
    # 용산구
    {"lat": 37.5326, "lng": 126.9906},
    # 성동구
    {"lat": 37.5635, "lng": 127.0369},
    # 광진구
    {"lat": 37.5384, "lng": 127.0822},
    # 동대문구
    {"lat": 37.5744, "lng": 127.0396},
    # 중랑구
    {"lat": 37.5882, "lng": 127.0924},
    # 성북구
    {"lat": 37.6066, "lng": 127.0177},
    # 강북구
    {"lat": 37.6396, "lng": 127.0253},
    # 도봉구
    {"lat": 37.6688, "lng": 127.0471},
    # 노원구
    {"lat": 37.6542, "lng": 127.0563},
    # 은평구
    {"lat": 37.6176, "lng": 126.9227},
    # 서대문구
    {"lat": 37.5791, "lng": 126.9368},
    # 마포구
    {"lat": 37.5663, "lng": 126.9019},
    # 강서구
    {"lat": 37.5509, "lng": 126.8496},
    # 구로구
    {"lat": 37.4954, "lng": 126.8876},
    # 관악구
    {"lat": 37.4784, "lng": 126.9516},
    # 서초구
    {"lat": 37.4836, "lng": 127.0327},
    # 강남구
    {"lat": 37.5172, "lng": 127.0473},
    # 송파구
    {"lat": 37.5145, "lng": 127.1059},
]
