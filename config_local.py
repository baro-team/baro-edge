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
    {"lat": 37.57042, "lng": 126.97524},
    {"lat": 37.5703, "lng": 126.97498},
    {"lat": 37.57054, "lng": 126.97884},
    {"lat": 37.57027, "lng": 126.97869},
    {"lat": 37.57032, "lng": 126.98167},
    {"lat": 37.56866, "lng": 126.98746},
    {"lat": 37.56944, "lng": 126.98775},
    {"lat": 37.57029, "lng": 126.98903},
    {"lat": 37.57023, "lng": 126.99001},
    {"lat": 37.57056, "lng": 126.99319},
    {"lat": 37.57034, "lng": 126.99362},
    {"lat": 37.571, "lng": 127.00116},
    {"lat": 37.57453, "lng": 127.0211},
    {"lat": 37.57307, "lng": 126.99791},
    {"lat": 37.58359, "lng": 126.99938},
    {"lat": 37.57936, "lng": 127.00225},
    {"lat": 37.57618, "lng": 127.00108},
    {"lat": 37.57585, "lng": 126.99986},
    {"lat": 37.5767, "lng": 126.98549},
    {"lat": 37.57318, "lng": 126.98299},
]
