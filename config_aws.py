# ================================================================
# AWS IoT Core 설정 (서울 리전)
# 실행: python vehicle_simulator.py --mode aws
# ================================================================
import os
from dotenv import load_dotenv

load_dotenv()

# MQTT - AWS IoT Core
MQTT_BROKER_HOST = os.getenv("IOT_ENDPOINT")
MQTT_BROKER_PORT = 8883

CERT_PATH = os.getenv("IOT_CERT_PATH")
KEY_PATH  = os.getenv("IOT_KEY_PATH")
CA_PATH   = os.getenv("IOT_CA_PATH")


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
    # 강남구
    {"lat": 37.5172, "lng": 127.0473},
    {"lat": 37.5045, "lng": 127.0244},
    # 서초구
    {"lat": 37.4836, "lng": 127.0327},
    {"lat": 37.4969, "lng": 127.0276},
    # 송파구
    {"lat": 37.5145, "lng": 127.1059},
    {"lat": 37.5030, "lng": 127.1178},
    # 강동구
    {"lat": 37.5492, "lng": 127.1463},
    {"lat": 37.5387, "lng": 127.1234},
    # 마포구
    {"lat": 37.5663, "lng": 126.9019},
    {"lat": 37.5482, "lng": 126.9127},
    # 서대문구
    {"lat": 37.5791, "lng": 126.9368},
    {"lat": 37.5642, "lng": 126.9435},
    # 은평구
    {"lat": 37.6176, "lng": 126.9227},
    {"lat": 37.6027, "lng": 126.9292},
    # 노원구
    {"lat": 37.6542, "lng": 127.0563},
    {"lat": 37.6435, "lng": 127.0719},
    # 도봉구
    {"lat": 37.6688, "lng": 127.0471},
    {"lat": 37.6524, "lng": 127.0327},
    # 강북구
    {"lat": 37.6396, "lng": 127.0253},
    {"lat": 37.6231, "lng": 127.0112},
    # 성북구
    {"lat": 37.6066, "lng": 127.0177},
    {"lat": 37.5892, "lng": 127.0085},
    # 중랑구
    {"lat": 37.5882, "lng": 127.0924},
    {"lat": 37.6063, "lng": 127.0812},
    # 동대문구
    {"lat": 37.5744, "lng": 127.0396},
    {"lat": 37.5823, "lng": 127.0541},
    # 광진구
    {"lat": 37.5384, "lng": 127.0822},
    {"lat": 37.5479, "lng": 127.0693},
    # 성동구
    {"lat": 37.5635, "lng": 127.0369},
    {"lat": 37.5513, "lng": 127.0441},
    # 중구
    {"lat": 37.5641, "lng": 126.9979},
    {"lat": 37.5573, "lng": 126.9973},
    # 종로구
    {"lat": 37.5730, "lng": 126.9794},
    {"lat": 37.5857, "lng": 126.9741},
    # 용산구
    {"lat": 37.5326, "lng": 126.9906},
    {"lat": 37.5443, "lng": 126.9745},
    # 관악구
    {"lat": 37.4784, "lng": 126.9516},
    {"lat": 37.4651, "lng": 126.9411},
    # 동작구
    {"lat": 37.5123, "lng": 126.9395},
    {"lat": 37.4985, "lng": 126.9479},
    # 양천구
    {"lat": 37.5171, "lng": 126.8665},
    {"lat": 37.5313, "lng": 126.8558},
    # 강서구
    {"lat": 37.5509, "lng": 126.8496},
    {"lat": 37.5631, "lng": 126.8227},
    # 구로구
    {"lat": 37.4954, "lng": 126.8876},
    {"lat": 37.4816, "lng": 126.8961},
    # 금천구
    {"lat": 37.4598, "lng": 126.9003},
    {"lat": 37.4474, "lng": 126.9018},
    # 영등포구
    {"lat": 37.5264, "lng": 126.8963},
    {"lat": 37.5153, "lng": 126.9046},
]
