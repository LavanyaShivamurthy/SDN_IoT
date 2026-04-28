#!/usr/bin/env python3
"""
Mqtt_Collector.py — All 4 Classes, ICU Scenario
====================================================
Class 1 → Emergency & Important       (ecg, pulse_oximeter, bp, fire)
Class 2 → Emergency but Not Important (emg, airflow, barometer, smoke)
Class 3 → Not Emergency but Important (infusion_pump, glucometer, gsr)
Class 4 → Not Emergency & Not Important (humidity, temperature, co)

Topology:
              Default Controller
                    |
                   S1 (Core)
                  /    \
              S2          S3
          h1–h8 (idle)  All sensors + broker + monitor
"""

from mininet.net import Mininet
from mininet.node import Controller, OVSSwitch
from mininet.link import TCLink
from mininet.log import setLogLevel, info
from datetime import datetime
import os
import sys
import time

sys.stdout.reconfigure(line_buffering=True)

# =====================================================================
# Configuration
# =====================================================================
BROKER_PORT     = 1883
BROKER_IP       = "10.0.0.2"
OUTPUT_DIR      = '/home/ictlab7/Documents/Learning_Mininet/pcap_captures'
OUTPUT_LOG_DIR  = '/home/ictlab7/Documents/Learning_Mininet/mqtt_capture'
EXPERIMENT_SEED = 2025
SCENARIO_NAME   = "s4"

os.makedirs(OUTPUT_DIR,     exist_ok=True)
os.makedirs(OUTPUT_LOG_DIR, exist_ok=True)


# =====================================================================
# Helpers
# =====================================================================

def start_tcpdump(node, intf):
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename  = f'{OUTPUT_DIR}/{node.name}_{intf}_{EXPERIMENT_SEED}_{SCENARIO_NAME}_{timestamp}.pcap'
    node.cmd(f'tcpdump -i {intf} -w {filename} &')
    info(f'*** Capturing {intf} on {node.name} -> {filename}\n')
    return filename


def start_mqtt_broker(host):
    info('*** Starting MQTT broker (Mosquitto)\n')
    conf_file = "/tmp/mosquitto_s4.conf"
    host.cmd(f"echo 'listener {BROKER_PORT} 0.0.0.0\nallow_anonymous true' > {conf_file}")
    host.cmd(f"mosquitto -c {conf_file} -v &")
    time.sleep(3)
    info(f"✅ MQTT broker started at {BROKER_IP}:{BROKER_PORT}\n")


def start_mqtt_subscriber(monitor):
    log_file = f"{OUTPUT_LOG_DIR}/sensor_subscriber_s4.log"
    monitor.cmd(f'python3 sensor_subscriber.py > {log_file} 2>&1 &')
    info(f"✅ MQTT subscriber started, log: {log_file}\n")


def start_publisher(host, sensor_name, class_label, interval_label):
    """Universal publisher launcher for all 4 classes."""
    log_file = f"{OUTPUT_LOG_DIR}/pub_{sensor_name}_s4.log"
    host.popen(
        ["python3", "sensor_publisher.py", BROKER_IP, "sensor", sensor_name],
        stdout=open(log_file, "w"),
        stderr=open(log_file.replace(".log", ".err"), "w")
    )
    info(f"[Class {class_label}] Publisher: {sensor_name} on {host.name} ({interval_label})\n")


def start_ping_monitor(monitor, target_ip):
    log_file = f"{OUTPUT_LOG_DIR}/monitor_ping_s4.log"
    monitor.cmd(f"ping {target_ip} > {log_file} 2>&1 &")
    info(f"📡 Ping monitor → {target_ip}\n")


def start_iperf_server(host):
    host.cmd("iperf -s -u -D")
    info(f"📡 iperf server on {host.name}\n")


def start_iperf_background(src, dst_ip, rate="2M"):
    src.cmd(f"iperf -u -c {dst_ip} -b {rate} -t 600 > /tmp/iperf_s4_bg.log 2>&1 &")
    info(f"📶 iperf background: {src.name} → {dst_ip} @ {rate}\n")


# =====================================================================
# Topology
# =====================================================================

def start_s4_network():
    net = Mininet(controller=Controller, switch=OVSSwitch,
                  link=TCLink, autoSetMacs=True)

    # ── Controller ────────────────────────────────────────────────────
    info('\n*** Adding controller\n')
    net.addController('c0')

    # ── Switches ──────────────────────────────────────────────────────
    s1 = net.addSwitch('s1')
    s2 = net.addSwitch('s2')
    s3 = net.addSwitch('s3')

    # ── Broker + Monitor ──────────────────────────────────────────────
    broker  = net.addHost('broker',  ip='10.0.0.2/8')
    monitor = net.addHost('monitor', ip='10.0.0.3/8')

    # ── Idle hosts on S2 ──────────────────────────────────────────────
    h1 = net.addHost('h1', ip='10.0.0.4/8')
    h2 = net.addHost('h2', ip='10.0.0.5/8')
    h3 = net.addHost('h3', ip='10.0.0.6/8')
    h4 = net.addHost('h4', ip='10.0.0.7/8')
    h5 = net.addHost('h5', ip='10.0.0.8/8')
    h6 = net.addHost('h6', ip='10.0.0.9/8')
    h7 = net.addHost('h7', ip='10.0.0.10/8')
    h8 = net.addHost('h8', ip='10.0.0.11/8')

    # ── Class 1: Emergency & Important ───────────────────────────────
    h_ecg   = net.addHost('h_ecg',   ip='10.0.0.12/8')  # ecg_monitor
    h_pulse = net.addHost('h_pulse', ip='10.0.0.13/8')  # pulse_oximeter
    h_bp    = net.addHost('h_bp',    ip='10.0.0.14/8')  # bp_sensor
    h_fire  = net.addHost('h_fire',  ip='10.0.0.15/8')  # fire_sensor

    # ── Class 2: Emergency but Not Important ──────────────────────────
    h_emg     = net.addHost('h_emg',     ip='10.0.0.16/8')  # emg_sensor
    h_airflow = net.addHost('h_airflow', ip='10.0.0.17/8')  # airflow_sensor
    h_baro    = net.addHost('h_baro',    ip='10.0.0.18/8')  # barometer
    h_smoke   = net.addHost('h_smoke',   ip='10.0.0.19/8')  # smoke_sensor

    # ── Class 3: Not Emergency but Important ──────────────────────────
    h_infusion = net.addHost('h_infusion', ip='10.0.0.20/8')  # infusion_pump
    h_glucose  = net.addHost('h_glucose',  ip='10.0.0.21/8')  # glucometer
    h_gsr      = net.addHost('h_gsr',      ip='10.0.0.22/8')  # gsr_sensor

    # ── Class 4: Not Emergency & Not Important ────────────────────────
    h_humidity = net.addHost('h_humidity', ip='10.0.0.23/8')  # humidity_sensor
    h_temp     = net.addHost('h_temp',     ip='10.0.0.24/8')  # temperature_sensor
    h_co       = net.addHost('h_co',       ip='10.0.0.25/8')  # co_sensor

    # ── Background traffic host ───────────────────────────────────────
    h_bg = net.addHost('h_bg', ip='10.0.0.26/8')

    # ── Links ─────────────────────────────────────────────────────────
    info('\n*** Creating links\n')
    net.addLink(s2, s1, bw=10)
    net.addLink(s3, s1, bw=10)
    net.addLink(broker,  s3, bw=10)
    net.addLink(monitor, s3, bw=10)

    # Idle hosts → S2
    for h in [h1, h2, h3, h4, h5, h6, h7, h8]:
        net.addLink(h, s2, bw=10)

    # Background → S2
    net.addLink(h_bg, s2, bw=10)

    # All sensor hosts → S3
    sensor_hosts = [
        h_ecg, h_pulse, h_bp, h_fire,          # Class 1
        h_emg, h_airflow, h_baro, h_smoke,      # Class 2
        h_infusion, h_glucose, h_gsr,           # Class 3
        h_humidity, h_temp, h_co,               # Class 4
    ]
    for h in sensor_hosts:
        net.addLink(h, s3, bw=10)

    # ── STEP 1: Start network ─────────────────────────────────────────
    info('\n*** Starting network\n')
    net.start()

    # ── STEP 2: Bring up ALL interfaces ───────────────────────────────
    info('\n*** Bringing up interfaces\n')
    all_hosts = [broker, monitor, h_bg,
                 h1, h2, h3, h4, h5, h6, h7, h8] + sensor_hosts
    for h in all_hosts:
        for intf in h.intfList():
            if 'lo' not in intf.name:
                h.cmd(f'ifconfig {intf} up')
    time.sleep(1)

    # ── STEP 3: Targeted connectivity check ───────────────────────────
    info('\n*** Verifying connectivity\n')
    net.ping([h_ecg, h_pulse, h_bp, h_fire,
              h_emg, h_airflow, h_baro, h_smoke,
              h_infusion, h_glucose, h_gsr,
              h_humidity, h_temp, h_co,
              broker])
    info("✅ Connectivity verified\n")

    # ── STEP 4: tcpdump ───────────────────────────────────────────────
    info('\n*** Starting tcpdump\n')
    start_tcpdump(broker, broker.defaultIntf())
    for intf in s3.intfList():
        if 'lo' not in intf.name:
            start_tcpdump(s3, intf)
            break
    start_tcpdump(h_ecg,  h_ecg.defaultIntf())   # Class 1 verification
    start_tcpdump(h_fire, h_fire.defaultIntf())   # Class 1 alert verification

    # ── STEP 5: Broker + subscriber ───────────────────────────────────
    start_mqtt_broker(broker)
    start_mqtt_subscriber(monitor)
    time.sleep(2)

    # ── STEP 6: Class 1 publishers (fastest — start first) ────────────
    info('\n*** Starting Class 1 publishers (Emergency & Important)\n')
    start_publisher(h_ecg,   "ecg_monitor",    "1", "0.5s")
    start_publisher(h_pulse, "pulse_oximeter", "1", "0.5s")
    start_publisher(h_bp,    "bp_sensor",      "1", "0.5s")
    start_publisher(h_fire,  "fire_sensor",    "1", "0.5s")
    info("🔴 Class 1 publishing at 0.5s interval\n")
    time.sleep(2)

    # ── STEP 7: Class 2 publishers ────────────────────────────────────
    info('\n*** Starting Class 2 publishers (Emergency but Not Important)\n')
    start_publisher(h_emg,     "emg_sensor",     "2", "0.8s")
    start_publisher(h_airflow, "airflow_sensor", "2", "0.8s")
    start_publisher(h_baro,    "barometer",      "2", "0.8s")
    start_publisher(h_smoke,   "smoke_sensor",   "2", "0.8s")
    info("🟠 Class 2 publishing at 0.8s interval\n")
    time.sleep(2)

    # ── STEP 8: Class 3 publishers ────────────────────────────────────
    info('\n*** Starting Class 3 publishers (Not Emergency but Important)\n')
    start_publisher(h_infusion, "infusion_pump", "3", "1.0s")
    start_publisher(h_glucose,  "glucometer",    "3", "1.0s")
    start_publisher(h_gsr,      "gsr_sensor",    "3", "1.0s")
    info("🟡 Class 3 publishing at 1.0s interval\n")
    time.sleep(2)

    # ── STEP 9: Class 4 publishers ────────────────────────────────────
    info('\n*** Starting Class 4 publishers (Not Emergency & Not Important)\n')
    start_publisher(h_humidity, "humidity_sensor",    "4", "2.0s")
    start_publisher(h_temp,     "temperature_sensor", "4", "2.0s")
    start_publisher(h_co,       "co_sensor",          "4", "2.0s")
    info("🟢 Class 4 publishing at 2.0s interval\n")
    time.sleep(2)

    # ── STEP 10: Background iperf + ping (starts LAST) ────────────────
    info('\n*** Starting background traffic\n')
    start_ping_monitor(monitor, BROKER_IP)
    start_iperf_server(broker)
    start_iperf_server(h1)
    start_iperf_background(h_bg, h1.IP(), rate="2M")
    info("📶 S4 background activated (2M iperf)\n")

    info("\n*** S4 running — Ctrl+C to stop ***\n")

    # ── Run loop ──────────────────────────────────────────────────────
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        info("\n*** Caught Ctrl+C, shutting down S4...\n")
    finally:
        info("\n*** Stopping all processes...\n")
        os.system("pkill -f iperf")
        os.system("pkill -f mosquitto")
        os.system("pkill -f tcpdump")
        os.system("pkill -f sensor_publisher.py")
        os.system("pkill -f ping")
        net.stop()
        info("\n*** S4 simulation ended cleanly.\n")


if __name__ == '__main__':
    setLogLevel('info')
    info("\n*** Starting S4 — All 4 Classes ICU Scenario ***\n")
    start_s4_network()
