#!/usr/bin/env python3

import paho.mqtt.client as mqtt
import sys, time, random, threading, os, json
from datetime import datetime

# ── Environment ─────────────────────────────────────────────
SCENARIO        = os.getenv("SCENARIO", "default")
SEED            = int(os.getenv("SEED", "2025"))
EMERGENCY_RATE  = os.getenv("EMERGENCY_RATE", "normal")

random.seed(SEED)

print(f"[DEBUG] SCENARIO={SCENARIO}")
print(f"[DEBUG] SEED={SEED}")
print(f"[DEBUG] EMERGENCY_RATE={EMERGENCY_RATE}")

# ── Args ────────────────────────────────────────────────────
if len(sys.argv) != 4:
    print("Usage: python3 sensor_publisher.py <BROKER_IP> <TOPIC> <SENSOR_NAME>")
    sys.exit(1)

BROKER_IP   = sys.argv[1]
TOPIC       = sys.argv[2]
SENSOR_NAME = sys.argv[3].lower()
BROKER_PORT = 1883

# ── Constants ───────────────────────────────────────────────
JITTER_PERCENT = 0.05
BURST_PROBABILITY = 0.05
BURST_COUNT_RANGE = (3, 8)

# ── Sensor Config ───────────────────────────────────────────
SENSOR_CONFIG = {
    "ecg_monitor": {"class":1,"unit":"bpm","min":60,"max":120,"interval":0.5},
    "pulse_oximeter": {"class":1,"unit":"%SpO2","min":85,"max":100,"interval":0.5},
    "bp_sensor": {"class":1,"unit":"mmHg","min":90,"max":180,"interval":0.5},
    "fire_sensor": {"class":1,"unit":"status","values":["OK","SMOKE","FIRE"],"interval":0.5},

    "emg_sensor": {"class":2,"unit":"mV","min":0,"max":10,"interval":0.8},
    "airflow_sensor": {"class":2,"unit":"L/s","min":0,"max":5,"interval":0.8},
    "barometer": {"class":2,"unit":"hPa","min":990,"max":1030,"interval":0.8},
    "smoke_sensor": {"class":2,"unit":"status","values":["CLEAR","SMOKE"],"interval":0.8},

    "infusion_pump": {"class":3,"unit":"mL/hr","min":5,"max":120,"interval":0.8},
    "glucometer": {"class":3,"unit":"mg/dL","min":70,"max":180,"interval":0.8},
    "gsr_sensor": {"class":3,"unit":"µS","min":0.1,"max":10,"interval":0.8},

    "humidity_sensor": {"class":4,"unit":"%","min":20,"max":80,"interval":2.0},
    "temperature_sensor": {"class":4,"unit":"°C","min":20,"max":35,"interval":2.0},
    "co_sensor": {"class":4,"unit":"ppm","min":0,"max":50,"interval":2.0},
}

ALIASES = {
    "ecg":"ecg_monitor","bp":"bp_sensor","pulse":"pulse_oximeter",
    "emg":"emg_sensor","airflow":"airflow_sensor","baro":"barometer",
    "smoke":"smoke_sensor","fire":"fire_sensor","infusion":"infusion_pump",
    "glucose":"glucometer","gsr":"gsr_sensor","humidity":"humidity_sensor",
    "temp":"temperature_sensor","co":"co_sensor"
}

QOS_MAP = {1:2, 2:1, 3:1, 4:0}

# ── Helpers ────────────────────────────────────────────────
def apply_jitter(base, rng):
    jitter = base * JITTER_PERCENT
    return max(0.01, rng.uniform(base - jitter, base + jitter))

def generate_value(cfg, rng):
    if "values" in cfg:
        return rng.choice(cfg["values"])
    return round(rng.uniform(cfg["min"], cfg["max"]), 2)

# ── Publisher ──────────────────────────────────────────────
def publish_sensor(sensor_key):

    cfg = SENSOR_CONFIG[sensor_key]
    class_id = cfg["class"]

    # Scenario-based interval
    base_interval = cfg["interval"]

    if EMERGENCY_RATE == "rare":
        base_interval *= 2.0
    elif EMERGENCY_RATE == "moderate":
        base_interval *= 1.2
    elif EMERGENCY_RATE == "bursty":
        base_interval *= 0.5

    rng = random.Random(SEED + hash(sensor_key) % 10000)

    client = mqtt.Client()
    client.connect(BROKER_IP, BROKER_PORT)
    client.loop_start()

    topic = f"sensor/{sensor_key}"

    print(f"[START] {sensor_key} | class={class_id} | interval={base_interval}")

    while True:
        value = generate_value(cfg, rng)
        HOST = os.getenv("HOSTNAME","unknown_host")
        print("Host",HOST)
        payload = json.dumps({
            "timestamp": time.time(),
            "sensor": sensor_key,
            "class": class_id,
            "value": value,
            "unit": cfg["unit"],
            "host":HOST
        })

        qos = QOS_MAP[class_id]

        try:
            # 🔥 Burst logic
            if class_id == 1 and rng.random() < BURST_PROBABILITY:
                burst = rng.randint(*BURST_COUNT_RANGE)
                print(f"[BURST] {sensor_key} x{burst}")
                for _ in range(burst):
                    client.publish(topic, payload, qos=qos)
                    time.sleep(0.05)

            client.publish(topic, payload, qos=qos)

        except Exception as e:
            print(f"[ERROR] {sensor_key}: {e}")

        sleep_time = apply_jitter(base_interval, rng)
        time.sleep(sleep_time)

# ── Main ───────────────────────────────────────────────────
def main():
    sensor_arg = SENSOR_NAME
    sensor_key = ALIASES.get(sensor_arg, sensor_arg)

    if sensor_key not in SENSOR_CONFIG:
        print("Invalid sensor:", sensor_arg)
        sys.exit(1)

    publish_sensor(sensor_key)

if __name__ == "__main__":
    main()
