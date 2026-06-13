import os

MQTT_HOST = os.environ.get("MQTT_HOST", "0.0.0.0")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MAX_CLIENTS = int(os.environ.get("MQTT_MAX_CLIENTS", "256"))

KEEPALIVE_MULTIPLIER = float(os.environ.get("MQTT_KEEPALIVE_MULTIPLIER", "2.0"))
TCP_KEEPIDLE = int(os.environ.get("MQTT_TCP_KEEPIDLE", "30"))
TCP_KEEPINTVL = int(os.environ.get("MQTT_TCP_KEEPINTVL", "10"))
TCP_KEEPCNT = int(os.environ.get("MQTT_TCP_KEEPCNT", "3"))

AUTH_CREDENTIALS = {
    "helmet_001": "helmet_key_001",
    "helmet_002": "helmet_key_002",
}
AUTH_ENABLED = os.environ.get("MQTT_AUTH_ENABLED", "true").lower() == "true"

DATA_LOG_ENABLED = True
DATA_LOG_DIR = os.environ.get("MQTT_DATA_LOG_DIR", "./data_logs")

ALERT_THRESHOLDS = {
    "temperature": {"min": 35.0, "max": 37.5},
    "heart_rate":  {"min": 40,   "max": 150},
    "velocity":    {"max": 20.0},
}

DATA_PIPELINE = [
    "validate",
    "threshold_check",
    "gps_geofence",
    "console_report",
    "persist",
]

LOG_LEVEL = os.environ.get("MQTT_LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
