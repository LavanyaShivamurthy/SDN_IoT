#!/usr/bin/env python3
"""
Mqtt_Collector.py — All 4 Classes, ICU Scenario
====================================================
Class 1 → Emergency & Important       (ecg, pulse_oximeter, bp, fire)
Class 2 → Emergency but Not Important (emg, airflow, barometer, smoke)
Class 3 → Not Emergency but Important (infusion_pump, glucometer, gsr)
Class 4 → Not Emergency & Not Important (humidity, temperature, co)

Topology:
               Rhy controller
                    |
                   S1 (Core)
                  /    \
              S2          S3
          h1–h8 (Addtional sensors)  All sensors + broker + monitor

=====================================================================
SCENARIO MATRIX
=====================================================================
  S1 — Baseline (MQTT only, no noise)
       MQTT=✔  iperf=✗  ping=✗  Emergency=Rare      Congestion=None

  S2 — Ping-augmented baseline
       MQTT=✔  iperf=✗  ping=✔  Emergency=Rare      Congestion=Minimal

  S3 — Moderate congestion
       MQTT=✔  iperf=✔(mod) ping=✔  Emergency=Moderate  Congestion=Partial

  S4 — Stress test (high congestion + emergency bursts)
       MQTT=✔  iperf=✔(high) ping=✔  Emergency=Bursty    Congestion=Severe

=====================================================================
TO SWITCH SCENARIO — change ONE line:
    SCENARIO_ID = 1   # 1 | 2 | 3 | 4
=====================================================================

Random seeds are fixed per run for reproducibility:
    SEED = SCENARIO_ID * 100 + 42
"""

# =====================================================================
# ▶▶▶  CHANGE THIS ONE LINE TO SWITCH SCENARIO  ◀◀◀
# =====================================================================
SCENARIO_ID = 3      # 1 | 2 | 3 | 4
# =====================================================================

import random
import numpy as np

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.log import setLogLevel, info
from datetime import datetime
import os, time, sys
from mininet.cli import CLI
sys.stdout.reconfigure(line_buffering=True)

# =====================================================================
# Reproducible seed (fixed per scenario)
# =====================================================================
#SEED = SCENARIO_ID * 100 + 42
SEED = SCENARIO_ID * 100 + 43

random.seed(SEED)
np.random.seed(SEED)
# =====================================================================
# Scenario definitions
# =====================================================================
SCENARIO_CONFIGS = {
    1: {
        "name":             "s1",
        "label":            "S1 — Baseline (MQTT only)",
        "use_iperf":        False,
        "use_ping":         False,
        "iperf_rate":       None,          # not used
        "emergency_rate":   "rare",        # passed to publisher as env var
        "congestion":       "none",
    },
    2: {
        "name":             "s2",
        "label":            "S2 — Ping-augmented baseline",
        "use_iperf":        False,
        "use_ping":         True,
        "iperf_rate":       None,
        "emergency_rate":   "rare",
        "congestion":       "minimal",
    },
    3: {
        "name":             "s3",
        "label":            "S3 — Moderate congestion",
        "use_iperf":        True,
        "use_ping":         True,
        "iperf_rate":       "1M",          # moderate
        "emergency_rate":   "moderate",
        "congestion":       "partial",
    },
    4: {
        "name":             "s4",
        "label":            "S4 — Stress test (high congestion + emergency bursts)",
        "use_iperf":        True,
        "use_ping":         True,
        "iperf_rate":       "2M",          # high
        "emergency_rate":   "bursty",
        "congestion":       "severe",
    },
}

# Pull active config
CFG           = SCENARIO_CONFIGS[SCENARIO_ID]
SCENARIO_NAME = CFG["name"]

# =====================================================================
# Static configuration
# =====================================================================
BROKER_PORT    = 1883
BROKER_IP      = "10.0.0.2"
OUTPUT_DIR     = '/home/ictlab7/Documents/Learning_Mininet/LSTM_Code/pcap_captures'
OUTPUT_LOG_DIR = '/home/ictlab7/Documents/Learning_Mininet/LSTM_Code/mqtt_capture'

os.makedirs(OUTPUT_DIR,     exist_ok=True)
os.makedirs(OUTPUT_LOG_DIR, exist_ok=True)


# =====================================================================
# Helpers
# =====================================================================

def start_tcpdump(node, intf):
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename  = (
        f'{OUTPUT_DIR}/{node.name}_{intf}_'
        f'{SEED}_{SCENARIO_NAME}_{timestamp}.pcap'
    )
    node.cmd(f'tcpdump -i {intf} -w {filename} &')
    info(f'*** Capturing {intf} on {node.name} -> {filename}\n')
    return filename


def start_mqtt_broker(host):
    info('*** Starting MQTT broker (Mosquitto)\n')
    conf_file = f"/tmp/mosquitto_{SCENARIO_NAME}.conf"
    host.cmd(
        f"echo 'listener {BROKER_PORT} 0.0.0.0\nallow_anonymous true' > {conf_file}"
    )
    host.cmd(f"mosquitto -c {conf_file} -v &")
    time.sleep(3)
    info(f"✅ MQTT broker started at {BROKER_IP}:{BROKER_PORT}\n")


def start_mqtt_subscriber(monitor):
    log_file = f"{OUTPUT_LOG_DIR}/sensor_subscriber_{SCENARIO_NAME}.log"
    #monitor.cmd(f'python3 sensor_subscriber.py')
    monitor.cmd(f'python3 sensor_subscriber.py > {log_file} 2>&1 &')
    info(f"✅ MQTT subscriber started, log: {log_file}\n")


def start_publisher(host, sensor_name, class_label, interval_label):
    """
    Universal publisher launcher for all 4 classes.

    Passes SCENARIO_NAME, SEED, and EMERGENCY_RATE as environment
    variables so sensor_publisher.py can adapt behaviour without
    requiring any code changes in that script.
    """
    log_file = f"{OUTPUT_LOG_DIR}/pub_{sensor_name}_{SCENARIO_NAME}.log"
    
    host_seed = SEED + abs((hash(host.name) % 1000))
    env_str = (
        f"SCENARIO={SCENARIO_NAME} "
        f"SEED={host_seed} "
        f"EMERGENCY_RATE={CFG['emergency_rate']} "
        f"INTERVAL={interval_label}"  f"HOSTNAME={host.name}"
    )

    host.cmd(f"{env_str} python3 -u sensor_publisher.py {BROKER_IP} sensor/{sensor_name} {sensor_name} " f">{log_file} 2>&1 & ")
    info(
        f"[Class {class_label}] Publisher: {sensor_name} on "
        f"{host.name} ({interval_label}) "
        f"[emergency={CFG['emergency_rate']}]\n"
     )


def start_ping_monitor(monitor, target_ip):
    if not CFG["use_ping"]:
        info("⏭  Ping monitoring disabled for this scenario\n")
        return
    log_file = f"{OUTPUT_LOG_DIR}/monitor_ping_{SCENARIO_NAME}.log"
    monitor.cmd(f"ping {target_ip} > {log_file} 2>&1 &")
    info(f"📡 Ping monitor → {target_ip}\n")


def start_iperf_server(host):
    if not CFG["use_iperf"]:
        return
    host.cmd("iperf -s -u -D")
    info(f"📡 iperf server on {host.name}\n")


def start_iperf_background(src, dst_ip):
    if not CFG["use_iperf"]:
        info("⏭  iperf background traffic disabled for this scenario\n")
        return
    rate    = CFG["iperf_rate"]
    log     = f"/tmp/iperf_{SCENARIO_NAME}_bg.log"
    src.cmd(f"iperf -u -c {dst_ip} -b {rate} -t 600 > {log} 2>&1 &")
    info(f"📶 iperf background: {src.name} → {dst_ip} @ {rate}\n")


# =====================================================================
# Topology
# =====================================================================

def start_network():
    net = Mininet(
        controller=None,
        switch=OVSSwitch,
        link=TCLink,
        autoSetMacs=True,
    )

    # ── Controller ────────────────────────────────────────────────────
    info('\n*** Adding controller\n')
    c0 = net.addController(
        'c0', controller=RemoteController, ip='127.0.0.1', port=6633
    )

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
    h_ecg   = net.addHost('h_ecg',   ip='10.0.0.12/8')
    h_pulse = net.addHost('h_pulse', ip='10.0.0.13/8')
    h_bp    = net.addHost('h_bp',    ip='10.0.0.14/8')
    h_fire  = net.addHost('h_fire',  ip='10.0.0.15/8')

    # ── Class 2: Emergency but Not Important ──────────────────────────
    h_emg     = net.addHost('h_emg',     ip='10.0.0.16/8')
    h_airflow = net.addHost('h_airflow', ip='10.0.0.17/8')
    h_baro    = net.addHost('h_baro',    ip='10.0.0.18/8')
    h_smoke   = net.addHost('h_smoke',   ip='10.0.0.19/8')

    # ── Class 3: Not Emergency but Important ──────────────────────────
    h_infusion = net.addHost('h_infusion', ip='10.0.0.20/8')
    h_glucose  = net.addHost('h_glucose',  ip='10.0.0.21/8')
    h_gsr      = net.addHost('h_gsr',      ip='10.0.0.22/8')

    # ── Class 4: Not Emergency & Not Important ────────────────────────
    h_humidity = net.addHost('h_humidity', ip='10.0.0.23/8')
    h_temp     = net.addHost('h_temp',     ip='10.0.0.24/8')
    h_co       = net.addHost('h_co',       ip='10.0.0.25/8')

    # ── Background traffic host ───────────────────────────────────────
    h_bg = net.addHost('h_bg', ip='10.0.0.26/8')

    # ── Links ─────────────────────────────────────────────────────────
    info('\n*** Creating links\n')
    net.addLink(s2, s1, bw=10)
    net.addLink(s3, s1, bw=10)
    net.addLink(broker,  s3, bw=10)
    net.addLink(monitor, s3, bw=10)

    for h in [h1, h2, h3, h4, h5, h6, h7, h8]:
        net.addLink(h, s2, bw=10)

    net.addLink(h_bg, s2, bw=10)

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
    time.sleep(2)

    # ── STEP 3: Connectivity check ────────────────────────────────────
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
    
    
    
    for h in sensor_hosts:
    	start_tcpdump(h, h.defaultIntf())
            
    start_tcpdump(h_ecg,  h_ecg.defaultIntf())
    start_tcpdump(h_fire, h_fire.defaultIntf())
    

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
    start_publisher(h1,   "ecg_monitor",    "1", "0.45s")
    start_publisher(h2, "bp_sensor", "1", "0.55s")
   
    info("🔴 Class 1 publishing at 0.5s interval\n")
    time.sleep(2)

    # ── STEP 7: Class 2 publishers ────────────────────────────────────
    info('\n*** Starting Class 2 publishers (Emergency but Not Important)\n')
    start_publisher(h_emg,     "emg_sensor",     "2", "0.8s")
    start_publisher(h_airflow, "airflow_sensor", "2", "0.8s")
    start_publisher(h_baro,    "barometer",      "2", "0.8s")
    start_publisher(h_smoke,   "smoke_sensor",   "2", "0.8s")
    start_publisher(h3,    "emg_sensor",      "2", "0.75s")
    start_publisher(h4,   "smoke_sensor",   "2", "0.85s")
    info("🟠 Class 2 publishing at 0.8s interval\n")
    time.sleep(2)

    # ── STEP 8: Class 3 publishers ────────────────────────────────────
    info('\n*** Starting Class 3 publishers (Not Emergency but Important)\n')
    start_publisher(h_infusion, "infusion_pump", "3", "1.0s")
    start_publisher(h_glucose,  "glucometer",    "3", "1.0s")
    start_publisher(h_gsr,      "gsr_sensor",    "3", "1.0s")
    start_publisher(h5,  "glucometer",    "3", "1.2s")
    start_publisher(h6,      "infusion_pump",    "3", "1.1s")
    info("🟡 Class 3 publishing at 1.0s interval\n")
    time.sleep(2)

    # ── STEP 9: Class 4 publishers ────────────────────────────────────
    info('\n*** Starting Class 4 publishers (Not Emergency & Not Important)\n')
    start_publisher(h_humidity, "humidity_sensor",    "4", "2.0s")
    start_publisher(h_temp,     "temperature_sensor", "4", "2.0s")
    start_publisher(h_co,       "co_sensor",          "4", "2.0s")
    start_publisher(h7,     "temperature_sensor", "4", "2.3s")
    start_publisher(h8,       "humidity_sensor",      "4", "2.5s")
    info("🟢 Class 4 publishing at 2.0s interval\n")
    time.sleep(2)

    # ── STEP 10: Background traffic (scenario-conditional) ────────────
    info('\n*** Starting background traffic\n')
    start_ping_monitor(monitor, BROKER_IP)   # skipped for S1
    start_iperf_server(broker)               # skipped for S1, S2
    start_iperf_server(h1)                   # skipped for S1, S2
    start_iperf_background(h_bg, h1.IP())    # skipped for S1, S2

    info(f"\n*** {CFG['label']} running — Ctrl+C to stop ***\n")
    info(f"    seed={SEED}  emergency={CFG['emergency_rate']}  "
         f"congestion={CFG['congestion']}\n")

    # ── Run loop ──────────────────────────────────────────────────────
    '''
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        info(f"\n*** Caught Ctrl+C, shutting down {SCENARIO_NAME}...\n")

    finally:
        info("\n*** Stopping all processes...\n")
        os.system("pkill -f iperf")
        os.system("pkill -f mosquitto")
        os.system("pkill -f tcpdump")
        os.system("pkill -f sensor_publisher.py")
        os.system("pkill -f ping")
        net.stop()
        info(f"\n*** {SCENARIO_NAME} simulation ended cleanly.\n")

    '''
    
    info(f"\n*** {CFG['label']} running ***\n")
    CLI(net)
    # Cleanup after exiting CLI
    info("\n*** Stopping all processes...\n")
    os.system("pkill -f iperf")
    os.system("pkill -f mosquitto")
    os.system("pkill -f tcpdump")
    os.system("pkill -f sensor_publisher.py")
    os.system("pkill -f ping")
    net.stop()
    info(f"\n*** {SCENARIO_NAME} simulation ended cleanly.\n")

# =====================================================================
# Entry point
# =====================================================================
if __name__ == '__main__':
    setLogLevel('info')
    info(f"\n*** Starting {CFG['label']} ***\n")
    info(f"    SCENARIO_ID={SCENARIO_ID}  SEED={SEED}\n")
    start_network()
