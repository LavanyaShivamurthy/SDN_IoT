#!/usr/bin/env python3
"""
sensor_publisher.py — All 4 Classes, ICU Scenario
===================================================
Class 1 → Emergency & Important       (0.5s)
Class 2 → Emergency but Not Important (0.8s)
Class 3 → Not Emergency but Important (1.0s)
Class 4 → Not Emergency & Not Important (2.0s)

"""

from logging.handlers import TimedRotatingFileHandler
import paho.mqtt.client as mqtt
import sys
import time
import random
from datetime import datetime
import threading
import logging
import signal

# ── Reproducibility ──────────────────────────────────────────────────────────
EXPERIMENT_SEED = 2025
random.seed(EXPERIMENT_SEED)

stop_event = threading.Event()

def handle_exit(sig, frame):
    print("\n[INFO] Ctrl+C received. Stopping S5 publisher...")
    stop_event.set()

signal.signal(signal.SIGINT, handle_exit)

# ── Logging  ──────────────────────────────────────
handler = TimedRotatingFileHandler(
    "sensors_publisher.log",
    when="H", interval=1, backupCount=48
)
logging.basicConfig(
    handlers=[handler],
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# ── Args ──────────────────────────────────────────────────────────────────────
if len(sys.argv) != 4:
    print("Usage: python3 sensor_publisher.py <BROKER_IP> <TOPIC> <SENSOR_NAME>")
    sys.exit(1)

BROKER_IP   = sys.argv[1]
TOPIC       = sys.argv[2]
SENSOR_NAME = sys.argv[3].lower()
BROKER_PORT = 1883
LOG_FILE    = f"/tmp/{SENSOR_NAME}_s5_publisher.log"

SENSOR_CONFIG = {
# ── Class 1: Emergency & Important ────────────────────────────────
    "ecg_monitor": {
        "class"   : 1,
        "unit"    : "bpm",
        "min"     : 60,
        "max"     : 120,
        "interval": 0.5,        # fast — critical vital sign
    },
    "pulse_oximeter": {
        "class"   : 1,
        "unit"    : "%SpO2",
        "min"     : 85,
        "max"     : 100,
        "interval": 0.5,
    },
    "bp_sensor": {
        "class"   : 1,
        "unit"    : "mmHg",
        "min"     : 90,
        "max"     : 180,
        "interval": 0.5,
    },
    "fire_sensor": {
        "class"   : 1,
        "unit"    : "status",
        "values"  : ["OK", "SMOKE_DETECTED", "FIRE_ALERT"],  # categorical
        "interval": 0.5,
    },

    # ── Class 2: Emergency but Not Important ──────────────────────────
    "emg_sensor": {
        "class"   : 2,
        "unit"    : "mV",
        "min"     : 0,
        "max"     : 10,
        "interval": 0.8,
    },
    "airflow_sensor": {
        "class"   : 2,
        "unit"    : "L/s",
        "min"     : 0,
        "max"     : 5,
        "interval": 0.8,
    },
    "barometer": {
        "class"   : 2,
        "unit"    : "hPa",
        "min"     : 990,
        "max"     : 1030,
        "interval": 0.8,
    },
    "smoke_sensor": {
        "class"   : 2,
        "unit"    : "status",
        "values"  : ["CLEAR", "SMOKE_DETECTED"],             # categorical
        "interval": 0.8,
    },

    # ── Class 3: Not Emergency but Important ──────────────────────────
    "infusion_pump": {
        "class"   : 3,
        "unit"    : "mL/hr",
        "min"     : 5,
        "max"     : 120,
        "interval": 1.0,
    },
    "glucometer": {
        "class"   : 3,
        "unit"    : "mg/dL",
        "min"     : 70,
        "max"     : 180,
        "interval": 1.0,
    },
    "gsr_sensor": {
        "class"   : 3,
        "unit"    : "µS",
        "min"     : 0.1,
        "max"     : 10,
        "interval": 1.0,
    },

    # ── Class 4: Not Emergency & Not Important ────────────────────────
    "humidity_sensor": {
        "class"   : 4,
        "unit"    : "%",
        "min"     : 20,
        "max"     : 80,
        "interval": 2.0,
    },
    "temperature_sensor": {
        "class"   : 4,
        "unit"    : "°C",
        "min"     : 20,
        "max"     : 35,
        "interval": 2.0,
    },
    "co_sensor": {
        "class"   : 4,
        "unit"    : "ppm",
        "min"     : 0,
        "max"     : 50,
        "interval": 2.0,
    },
}

ALIASES = {
    "ecg"      : "ecg_monitor",
    "bp"       : "bp_sensor",
    "oxygen"   : "pulse_oximeter",
    "pulse"    : "pulse_oximeter",
    "emg"      : "emg_sensor",
    "airflow"  : "airflow_sensor",
    "baro"     : "barometer",
    "smoke"    : "smoke_sensor",
    "fire"     : "fire_sensor",
    "infusion" : "infusion_pump",
    "glucose"  : "glucometer",
    "gsr"      : "gsr_sensor",
    "humidity" : "humidity_sensor",
    "temp"     : "temperature_sensor",
    "co"       : "co_sensor",
}


ADMIN_VALUES   = ["sync", "idle", "config", "heartbeat_ok"]
ADMIN_INTERVAL = 15.0   


def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {msg}\n")
    print(f"[{timestamp}] {msg}", flush=True)

def generate_value(cfg, rng):
    """Handle both numeric (min/max) and categorical (values) sensors."""
    if "values" in cfg:
        # Categorical sensor — weighted towards normal state
        weights = [0.85] + [0.15 / (len(cfg["values"]) - 1)] * (len(cfg["values"]) - 1)
        return rng.choices(cfg["values"], weights=weights, k=1)[0]
    else:
        return round(rng.uniform(cfg["min"], cfg["max"]), 2)

def publish_sensor(sensor_key, topic, broker_ip, broker_port):
    cfg      = SENSOR_CONFIG[sensor_key]
    class_id = cfg["class"]

    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)

  
    sensor_seed = EXPERIMENT_SEED + hash(sensor_key) % 10000
    rng = random.Random(sensor_seed)

    try:
        client.connect(broker_ip, broker_port)
        log(f"[Publisher] Connected to {broker_ip}:{broker_port}, "
            f"topic '{topic}' as {sensor_key} (Class={class_id}, interval={cfg['interval']}s)")
        client.loop_start()
    except Exception as e:
        log(f"[Publisher] Connection failed for {sensor_key}: {e}")
        return

    sensor_topic    = f"sensor/{sensor_key}"
    last_admin_time = time.time()

    while not stop_event.is_set():
        
        value   = generate_value(cfg, rng)
        payload = f"{sensor_key}:{value}{cfg['unit']}:Class={class_id}"

        try:
            client.publish(sensor_topic, payload, qos=1)
            log(f"[Publisher] {sensor_key}: {payload}")
        except Exception as e:
            log(f"[Publisher] {sensor_key}: Publish failed: {e}")

        # Admin heartbeat 
        if time.time() - last_admin_time >= ADMIN_INTERVAL:
            admin_value = rng.choice(ADMIN_VALUES)
            try:
                client.publish("admin/heartbeat", admin_value, qos=0)
                log(f"[Publisher] (Admin) {admin_value}")
                last_admin_time = time.time()
            except Exception as e:
                log(f"[Publisher] {sensor_key}: Admin publish failed: {e}")

        log(f"[SeedConfig] Sensor={sensor_key}, Seed={sensor_seed}")
        time.sleep(cfg["interval"])   # 1.0s instead of 2.5s

    client.loop_stop()
    client.disconnect()
    log(f"[Publisher] {sensor_key}: Stopped cleanly.")


def main():
    sensor_arg = sys.argv[3].lower()
    broker_ip  = sys.argv[1]
    topic      = sys.argv[2]

    # Resolve alias
    sensor_key = ALIASES.get(sensor_arg, sensor_arg)

    if sensor_key not in SENSOR_CONFIG:
        log(f"[Publisher] ERROR: Unknown sensor '{sensor_arg}'.")
        log(f"[Publisher] Valid sensors: {list(SENSOR_CONFIG.keys())}")
        sys.exit(1)

    log(f"[Publisher] Starting  publisher for: {sensor_key} "
        f"(interval={SENSOR_CONFIG[sensor_key]['interval']}s, )")
    publish_sensor(sensor_key, topic, broker_ip, BROKER_PORT)


if __name__ == "__main__":
    main()
