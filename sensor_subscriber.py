#!/usr/bin/env python3

import paho.mqtt.client as mqtt
import json
import csv
import time
from datetime import datetime

BROKER_IP = "10.0.0.2"
PORT = 1883
CSV_FILE = "sensor_data.csv"

# Create CSV with header
with open(CSV_FILE, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["timestamp", "sensor", "class", "value", "unit", "topic"])


def on_connect(client, userdata, flags, rc, properties=None):
    print("[Subscriber] Connected", flush=True)
    
    # ✅ Wildcard subscription (IMPORTANT)
    client.subscribe("sensor/#", qos=1)


def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())

        print(f"[DEBUG] Topic={msg.topic}", flush=True)
        print(f"[DEBUG] Payload={payload}", flush=True)
        print(f"HOST : {payload.get('host')}", flush=True)
        if not isinstance(payload, dict):
            print("[DROP] Payload not dict")
            return
        if "value" not in payload:
            print("[DROP] Missing value field", flush=True)
            return

        # 🔥 Extract sensor from topic (correct way)
        parts = msg.topic.split('/')
           # MUST be exactly: sensor/<name>
        if len(parts) != 2 or parts[1] in ["","#"]:
            print(f"[DROP] Bad topic format: {msg.topic}", flush=True)
            print("\n🚨 INVALID TOPIC DETECTED", flush=True)
            print(f"TOPIC   : {msg.topic}", flush=True)
            print(f"PAYLOAD : {payload}", flush=True)
            return

        if parts[0] != "sensor":
            print(f"[DROP] Not sensor topic: {msg.topic}", flush=True)
            return

        if parts[1] in ["", "#"]:
            print(f"[DROP] Invalid sensor name: {msg.topic}", flush=True)
            return
        sensor = parts[1]
        # 🚨 Detect mismatch
        if payload.get("sensor") != sensor:
            print("\n⚠️ SENSOR MISMATCH", flush=True)
            print(f"TOPIC   : {msg.topic}", flush=True)
            print(f"PAYLOAD : {payload}", flush=True)



        timestamp = payload.get("timestamp", time.time())
        class_id  = payload.get("class", -1)
        value     = payload.get("value", None)
        unit      = payload.get("unit", "")

        # Detect bad publishers
        if payload.get("sensor") != sensor:
            print(f"[MISMATCH] Topic={msg.topic}, Payload={payload}", flush=True)

        ts_readable = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")

        with open(CSV_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([ts_readable, sensor, class_id, value, unit, msg.topic])

    except Exception as e:
        print("[ERROR]", e)
        print("\n❌ JSON ERROR",flush=True)
        print(f"TOPIC RAW: {msg.topic}", flush=True)
        print(f"PAYLOAD RAW: {msg.payload}", flush=True) 


def main():
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)

    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(BROKER_IP, PORT)
    print("🚀 Subscriber script started", flush=True)
    client.loop_forever()


if __name__ == "__main__":
    main()
