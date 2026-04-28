"""
Pcap_To_csv_Summary.py
======================
ICU MQTT Sensor – 4-Class Classification Pipeline
--------------------------------------------------
Class 1 → Emergency & Important       : ecg, pulse_oximeter, bp, fire
Class 2 → Emergency but Not Important : emg, airflow, barometer, smoke
Class 3 → Not Emergency but Important : infusion_pump, glucometer, gsr
Class 4 → Not Emergency & Not Important: humidity, temperature, co

Pipeline
--------
1. Run extract_pcap_to_csv.sh for every .pcap/.pcapng in PCAP_DIR
2. Merge all *_rawData.csv files
3. Engineer LSTM + CNN features
4. Assign class labels from mqtt.topic
5. Deduplicate
6. Save cleaned dataset
7. Print / save rich dataset summary (per-sensor & per-class analysis)
"""

import os
import math
import subprocess
import time
from collections import Counter

import numpy as np
import pandas as pd

# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════
BASE_DIR       = "/home/ictlab7/Documents/Learning_Mininet/LSTM_Code"
PCAP_DIR       = os.path.join(BASE_DIR, "pcap_captures")
CSV_DIR        = os.path.join(BASE_DIR, "csvLSTM")
EXTRACT_SCRIPT = os.path.join(BASE_DIR, "extract_pcap_to_csv.sh")

OUTPUT_FILE  = os.path.join(CSV_DIR, "icu_all_classes_clean.csv")
SUMMARY_FILE = os.path.join(CSV_DIR, "icu_dataset_summary.txt")

# ── ICU sensor → class mapping ──────────────────────────────
# Keys are the last segment of the mqtt.topic (case-insensitive).
# Add aliases here if your Collector.py uses different topic names.
CLASS_MAP = {
    # Class 1 – Emergency & Important
    "ecg":           1,
    "pulse_oximeter":1,
    "bp":            1,
    "fire":          1,

    # Class 2 – Emergency but Not Important
    "emg":           2,
    "airflow":       2,
    "barometer":     2,
    "smoke":         2,

    # Class 3 – Not Emergency but Important
    "infusion_pump": 3,
    "glucometer":    3,
    "gsr":           3,

    # Class 4 – Not Emergency & Not Important
    "humidity":      4,
    "temperature":   4,
    "co":            4,
}

CLASS_LABELS = {
    1: "Emergency & Important",
    2: "Emergency but Not Important",
    3: "Not Emergency but Important",
    4: "Not Emergency & Not Important",
}

# All sensors grouped by class (for summary display)
CLASS_SENSORS = {
    1: ["ecg", "pulse_oximeter", "bp", "fire"],
    2: ["emg", "airflow", "barometer", "smoke"],
    3: ["infusion_pump", "glucometer", "gsr"],
    4: ["humidity", "temperature", "co"],
}

# Deduplication key – unique packet identity
DUPLICATE_KEYS = [
    "frame.time_epoch", "ip.src", "ip.dst",
    "tcp.srcport", "tcp.dstport", "frame.len",
]

os.makedirs(CSV_DIR, exist_ok=True)


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _payload_entropy(hex_str) -> float:
    """Shannon entropy of MQTT payload bytes (tshark hex-colon format)."""
    if not isinstance(hex_str, str) or not hex_str.strip():
        return 0.0
    cleaned = hex_str.replace(":", "").replace(" ", "")
    try:
        data = bytes.fromhex(cleaned)
    except ValueError:
        return 0.0
    if not data:
        return 0.0
    counts = Counter(data)
    total  = len(data)
    return -sum((c / total) * math.log2(c / total) for c in counts.values())


def _extract_sensor_name(topic) -> str:
    """
    Return the last non-empty segment of an MQTT topic path.
    'icu/sensor/temperature' → 'temperature'
    """
    if not isinstance(topic, str) or not topic.strip():
        return "unknown"
    parts = [p for p in topic.strip("/").split("/") if p]
    return parts[-1].lower() if parts else "unknown"


def _topic_to_class(sensor_name: str) -> int:
    """Map a sensor name to its ICU class (1-4). Returns 0 if unknown."""
    return CLASS_MAP.get(sensor_name.lower(), 0)


def _safe_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _flags_to_int(val) -> int:
    if pd.isna(val):
        return 0
    s = str(val).strip()
    try:
        return int(s, 16)
    except ValueError:
        return 0


# ═══════════════════════════════════════════════════════════════
# STEP 1 – RUN EXTRACTION SCRIPT
# ═══════════════════════════════════════════════════════════════

def run_extraction_script() -> bool:
    print("=" * 60)
    print(" STEP 1 – PCAP EXTRACTION")
    print("=" * 60)
    print(f"  Script : {EXTRACT_SCRIPT}")
    print(f"  PCAPs  : {PCAP_DIR}")
    print(f"  CSVs   : {CSV_DIR}")
    print()

    for path, label in [(EXTRACT_SCRIPT, "script"), (PCAP_DIR, "PCAP dir")]:
        if not os.path.exists(path):
            print(f"❌ {label} not found: {path}")
            return False

    pcap_files = sorted(
        os.path.join(PCAP_DIR, f)
        for f in os.listdir(PCAP_DIR)
        if f.lower().endswith((".pcap", ".pcapng"))
    )

    if not pcap_files:
        print(f"❌ No PCAP files in {PCAP_DIR}")
        return False

    print(f"  Found {len(pcap_files)} PCAP file(s)")
    ok, fail = 0, 0

    for pcap in pcap_files:
        print(f"\n  ▶ {os.path.basename(pcap)}")
        try:
            res = subprocess.run(
                ["bash", EXTRACT_SCRIPT, pcap],
                capture_output=True, text=True, cwd=BASE_DIR,
            )
            # Print tshark-level output (strip noisy blank lines)
            for line in res.stdout.strip().splitlines():
                if line.strip():
                    print(f"    {line}")
            if res.returncode != 0:
                if res.stderr.strip():
                    print(f"    ⚠ stderr: {res.stderr.strip()[:200]}")
                print(f"    ❌ exit code {res.returncode} – skipping")
                fail += 1
            else:
                ok += 1
        except Exception as exc:
            print(f"    ❌ Exception: {exc}")
            fail += 1

    print(f"\n  ✔ {ok} succeeded, {fail} failed")
    return ok > 0


# ═══════════════════════════════════════════════════════════════
# STEP 2 – MERGE RAW CSVs
# ═══════════════════════════════════════════════════════════════

def merge_csvs() -> pd.DataFrame | None:
    print("\n" + "=" * 60)
    print(" STEP 2 – MERGE CSVs")
    print("=" * 60)

    csv_files = sorted(
        os.path.join(CSV_DIR, f)
        for f in os.listdir(CSV_DIR)
        if f.endswith("_rawData.csv")
    )

    if not csv_files:
        print("❌ No *_rawData.csv found – did extraction succeed?")
        return None

    frames = []
    for path in csv_files:
        try:
            df = pd.read_csv(path, low_memory=False)
            df["source_file"] = os.path.basename(path)
            frames.append(df)
            print(f"  ✔ {os.path.basename(path):45s}  {len(df):>8,} rows")
        except Exception as exc:
            print(f"  ⚠ Skipping {os.path.basename(path)}: {exc}")

    if not frames:
        return None

    merged = pd.concat(frames, ignore_index=True)
    print(f"\n  Total rows after merge: {len(merged):,}")
    return merged


# ═══════════════════════════════════════════════════════════════
# STEP 3 – FEATURE ENGINEERING
# ═══════════════════════════════════════════════════════════════

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Derives LSTM-temporal and CNN-structural features.

    LSTM (sequence / temporal)
    ──────────────────────────
    flow_id              Bidirectional 4-tuple key for grouping sequences
    inter_arrival_time   Time gap between consecutive packets in a flow
    flow_packet_rank     Packet's ordinal position within its flow
    bytes_per_second     Instantaneous throughput (frame.len / IAT)
    cumulative_bytes     Running byte total per flow (session volume)

    CNN (point-in-time / structural)
    ──────────────────────────────────
    payload_entropy      Shannon entropy of mqtt.msg hex bytes
    header_ratio         tcp.hdr_len / frame.len
    tcp_flags_int        TCP flags bitmap as integer
    payload_len          mqtt.len (cleaned numeric)
    is_mqtt              1 if frame.protocols contains 'mqtt'
    ip_proto_norm        ip.proto normalised to [0,1] (max=255)

    Classification helpers
    ──────────────────────
    sensor_name          Last segment of mqtt.topic (e.g. 'temperature')
    icu_class            ICU class 1-4 (0 = unknown / non-MQTT)
    class_label          Human-readable class description
    """
    print("\n" + "=" * 60)
    print(" STEP 3 – FEATURE ENGINEERING")
    print("=" * 60)

    # ── Coerce numerics ───────────────────────────────────
    num_cols = [
        "frame.time_epoch", "frame.time_delta", "frame.time_relative",
        "frame.len", "frame.cap_len",
        "ip.len", "ip.ttl", "ip.proto",
        "tcp.len", "tcp.window_size", "tcp.seq", "tcp.ack", "tcp.hdr_len",
        "udp.length", "mqtt.qos", "mqtt.msgtype", "mqtt.len",
    ]
    for col in num_cols:
        if col in df.columns:
            df[col] = _safe_num(df[col])

    # ── Sort by time ──────────────────────────────────────
    if "frame.time_epoch" in df.columns:
        df.sort_values("frame.time_epoch", inplace=True)
        df.reset_index(drop=True, inplace=True)

    # ── flow_id (bidirectional) ───────────────────────────
    src_port = df.get("tcp.srcport", df.get("udp.srcport", pd.Series("", index=df.index)))
    dst_port = df.get("tcp.dstport", df.get("udp.dstport", pd.Series("", index=df.index)))

    def _make_flow_id(row):
        a = (str(row.get("ip.src", "")), str(src_port.iloc[row.name] if hasattr(src_port, 'iloc') else ""))
        b = (str(row.get("ip.dst", "")), str(dst_port.iloc[row.name] if hasattr(dst_port, 'iloc') else ""))
        lo, hi = sorted([a, b])
        return f"{lo[0]}:{lo[1]}-{hi[0]}:{hi[1]}"

    df["flow_id"] = (
        df["ip.src"].fillna("") + ":" +
        src_port.fillna("").astype(str) + "-" +
        df["ip.dst"].fillna("") + ":" +
        dst_port.fillna("").astype(str)
    )

    # ── inter_arrival_time ────────────────────────────────
    if "frame.time_epoch" in df.columns:
        df["inter_arrival_time"] = (
            df.groupby("flow_id")["frame.time_epoch"]
            .diff()
            .fillna(0)
            .clip(lower=0)
        )

    # ── flow_packet_rank ──────────────────────────────────
    df["flow_packet_rank"] = df.groupby("flow_id").cumcount() + 1

    # ── bytes_per_second ──────────────────────────────────
    if "frame.len" in df.columns and "inter_arrival_time" in df.columns:
        df["bytes_per_second"] = np.where(
            df["inter_arrival_time"] > 0,
            df["frame.len"] / df["inter_arrival_time"],
            0.0,
        )

    # ── cumulative_bytes per flow ─────────────────────────
    if "frame.len" in df.columns:
        df["cumulative_bytes"] = df.groupby("flow_id")["frame.len"].cumsum()

    # ── payload_entropy ───────────────────────────────────
    if "mqtt.msg" in df.columns:
        df["payload_entropy"] = df["mqtt.msg"].apply(_payload_entropy)
    else:
        df["payload_entropy"] = 0.0

    # ── header_ratio ──────────────────────────────────────
    if "tcp.hdr_len" in df.columns and "frame.len" in df.columns:
        df["header_ratio"] = np.where(
            df["frame.len"] > 0,
            df["tcp.hdr_len"].fillna(0) / df["frame.len"],
            0.0,
        )
    else:
        df["header_ratio"] = 0.0

    # ── tcp_flags_int ─────────────────────────────────────
    if "tcp.flags" in df.columns:
        df["tcp_flags_int"] = df["tcp.flags"].apply(_flags_to_int)
    else:
        df["tcp_flags_int"] = 0

    # ── payload_len ───────────────────────────────────────
    if "mqtt.len" in df.columns:
        df["payload_len"] = df["mqtt.len"].fillna(0).astype(int)
    else:
        df["payload_len"] = 0

    # ── is_mqtt ───────────────────────────────────────────
    if "frame.protocols" in df.columns:
        df["is_mqtt"] = (
            df["frame.protocols"]
            .str.contains("mqtt", case=False, na=False)
            .astype(int)
        )
    else:
        df["is_mqtt"] = 0

    # ── ip_proto_norm ─────────────────────────────────────
    if "ip.proto" in df.columns:
        df["ip_proto_norm"] = df["ip.proto"].fillna(0) / 255.0
    else:
        df["ip_proto_norm"] = 0.0

    # ── sensor_name ───────────────────────────────────────
    if "mqtt.topic" in df.columns:
        df["sensor_name"] = df["mqtt.topic"].apply(_extract_sensor_name)
    else:
        df["sensor_name"] = "unknown"

    # ── ICU class label ───────────────────────────────────
    df["icu_class"]   = df["sensor_name"].apply(_topic_to_class)
    df["class_label"] = df["icu_class"].map(CLASS_LABELS).fillna("Unknown")

    n_labeled   = (df["icu_class"] > 0).sum()
    n_unlabeled = (df["icu_class"] == 0).sum()
    print(f"  Labelled packets   : {n_labeled:,}")
    print(f"  Unlabelled (class 0): {n_unlabeled:,}  "
          f"(non-MQTT / unrecognised sensor)")
    print(f"  Total columns now  : {len(df.columns)}")
    return df


# ═══════════════════════════════════════════════════════════════
# STEP 4 – DEDUPLICATION
# ═══════════════════════════════════════════════════════════════

def deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    print("\n" + "=" * 60)
    print(" STEP 4 – DEDUPLICATION")
    print("=" * 60)
    keys = [k for k in DUPLICATE_KEYS if k in df.columns]
    if not keys:
        print("  ⚠ No key columns found – skipping")
        return df
    before = len(df)
    df.drop_duplicates(subset=keys, inplace=True)
    df.reset_index(drop=True, inplace=True)
    print(f"  Removed {before - len(df):,} duplicates  →  {len(df):,} rows remain")
    return df


# ═══════════════════════════════════════════════════════════════
# STEP 5 – SAVE
# ═══════════════════════════════════════════════════════════════

def save_dataset(df: pd.DataFrame) -> None:
    df.to_csv(OUTPUT_FILE, index=False)
    print(f"\n  💾 Saved → {OUTPUT_FILE}")
    print(f"     {len(df):,} rows × {len(df.columns)} columns")


# ═══════════════════════════════════════════════════════════════
# STEP 6 – RICH SUMMARY
# ═══════════════════════════════════════════════════════════════

def summarize_dataset(df: pd.DataFrame, elapsed: float) -> None:
    print("\n" + "=" * 60)
    print(" STEP 6 – DATASET SUMMARY")
    print("=" * 60)

    lines = []

    def h(title: str):
        lines.append("")
        lines.append("╔" + "═" * 58 + "╗")
        lines.append(f"║  {title:<56}║")
        lines.append("╚" + "═" * 58 + "╝")

    def row(label: str, value: str):
        lines.append(f"  {label:<38} {value}")

    def sub(text: str):
        lines.append(f"  ── {text}")

    # ── Overview ──────────────────────────────────────────
    h("OVERVIEW")
    row("Total packets",              f"{len(df):,}")
    row("Total feature columns",      f"{len(df.columns)}")
    row("Processing time (s)",        f"{elapsed:.1f}")
    if "frame.time_epoch" in df.columns:
        t = df["frame.time_epoch"].dropna()
        dur = t.max() - t.min()
        row("Capture duration (s)",   f"{dur:.2f}")
        row("Avg packet rate (pkt/s)",f"{len(df) / max(dur, 1):.1f}")
    row("MQTT packets",
        f"{df['is_mqtt'].sum():,}  ({100*df['is_mqtt'].mean():.1f}%)"
        if "is_mqtt" in df.columns else "N/A")
    row("Output CSV", OUTPUT_FILE)

    # ── Per-source file ───────────────────────────────────
    if "source_file" in df.columns:
        h("PACKETS PER SOURCE FILE")
        for fname, cnt in df["source_file"].value_counts().items():
            row(str(fname), f"{cnt:,}")

    # ── Protocol breakdown ────────────────────────────────
    if "frame.protocols" in df.columns:
        h("PROTOCOL STACK (TOP 15)")
        for proto, cnt in df["frame.protocols"].value_counts().head(15).items():
            row(str(proto), f"{cnt:,}")

    # ── CLASS DISTRIBUTION ────────────────────────────────
    if "icu_class" in df.columns:
        h("ICU CLASS DISTRIBUTION")
        total_labelled = (df["icu_class"] > 0).sum()
        for cls in sorted(CLASS_LABELS):
            cnt  = (df["icu_class"] == cls).sum()
            pct  = 100 * cnt / max(total_labelled, 1)
            sensors = ", ".join(CLASS_SENSORS[cls])
            row(f"Class {cls}: {CLASS_LABELS[cls]}", f"{cnt:,}  ({pct:.1f}%)")
            lines.append(f"       Sensors: {sensors}")
        unlab = (df["icu_class"] == 0).sum()
        row("Class 0: Unknown / Non-MQTT", f"{unlab:,}")

    # ── Per-sensor packet count ───────────────────────────
    if "sensor_name" in df.columns:
        h("PER-SENSOR PACKET COUNT")
        sensor_counts = (
            df[df["sensor_name"] != "unknown"]["sensor_name"]
            .value_counts()
        )
        for sensor, cnt in sensor_counts.items():
            cls   = CLASS_MAP.get(sensor, 0)
            label = CLASS_LABELS.get(cls, "Unknown")
            row(f"{sensor:25s} [Class {cls}]", f"{cnt:,}")

    # ── Per-sensor payload stats ──────────────────────────
    if "sensor_name" in df.columns and "payload_len" in df.columns:
        h("PER-SENSOR PAYLOAD LENGTH (bytes)")
        sub("count | mean | min | max")
        grp = (
            df[df["sensor_name"] != "unknown"]
            .groupby("sensor_name")["payload_len"]
            .agg(["count", "mean", "min", "max"])
            .sort_values("count", ascending=False)
        )
        for sensor, r in grp.iterrows():
            row(str(sensor),
                f"n={int(r['count']):,}  "
                f"mean={r['mean']:.1f}  "
                f"min={int(r['min'])}  "
                f"max={int(r['max'])}")

    # ── Per-sensor QoS breakdown ──────────────────────────
    if "sensor_name" in df.columns and "mqtt.qos" in df.columns:
        h("PER-SENSOR MQTT QoS BREAKDOWN")
        mqtt_df = df[(df["sensor_name"] != "unknown") & df["mqtt.qos"].notna()]
        for sensor in sorted(mqtt_df["sensor_name"].unique()):
            qos_counts = (
                mqtt_df[mqtt_df["sensor_name"] == sensor]["mqtt.qos"]
                .value_counts()
                .sort_index()
            )
            qos_str = "  ".join(f"QoS{int(k)}={v}" for k, v in qos_counts.items())
            row(str(sensor), qos_str if qos_str else "–")

    # ── Per-class inter-arrival stats ─────────────────────
    if "icu_class" in df.columns and "inter_arrival_time" in df.columns:
        h("PER-CLASS INTER-ARRIVAL TIME (s)")
        sub("mean | std | min | max")
        for cls in sorted(CLASS_LABELS):
            subset = df[df["icu_class"] == cls]["inter_arrival_time"]
            if len(subset) == 0:
                continue
            row(f"Class {cls}: {CLASS_LABELS[cls][:25]}",
                f"mean={subset.mean():.4f}  "
                f"std={subset.std():.4f}  "
                f"min={subset.min():.4f}  "
                f"max={subset.max():.4f}")

    # ── Per-class payload entropy ─────────────────────────
    if "icu_class" in df.columns and "payload_entropy" in df.columns:
        h("PER-CLASS PAYLOAD ENTROPY")
        sub("mean | std | min | max")
        for cls in sorted(CLASS_LABELS):
            subset = df[df["icu_class"] == cls]["payload_entropy"]
            if len(subset) == 0:
                continue
            row(f"Class {cls}: {CLASS_LABELS[cls][:25]}",
                f"mean={subset.mean():.3f}  "
                f"std={subset.std():.3f}  "
                f"min={subset.min():.3f}  "
                f"max={subset.max():.3f}")

    # ── MQTT message type distribution ────────────────────
    MQTT_TYPES = {
        1:"CONNECT", 2:"CONNACK",  3:"PUBLISH",  4:"PUBACK",
        5:"PUBREC",  6:"PUBREL",   7:"PUBCOMP",  8:"SUBSCRIBE",
        9:"SUBACK", 10:"UNSUBSCRIBE",11:"UNSUBACK",12:"PINGREQ",
       13:"PINGRESP",14:"DISCONNECT",
    }
    if "mqtt.msgtype" in df.columns:
        h("MQTT MESSAGE TYPE DISTRIBUTION")
        for mtype, cnt in df["mqtt.msgtype"].dropna().value_counts().items():
            label = MQTT_TYPES.get(int(mtype), f"TYPE_{int(mtype)}")
            row(f"  {label} ({int(mtype)})", f"{cnt:,}")

    # ── LSTM / CNN feature statistics ─────────────────────
    eng_feats = [
        "inter_arrival_time", "bytes_per_second", "flow_packet_rank",
        "cumulative_bytes", "payload_entropy", "header_ratio",
        "tcp_flags_int", "payload_len", "ip_proto_norm",
    ]
    present = [c for c in eng_feats if c in df.columns]
    if present:
        h("LSTM / CNN FEATURE STATISTICS")
        sub("mean | std | min | max")
        desc = df[present].describe().T[["mean", "std", "min", "max"]]
        for feat, r in desc.iterrows():
            row(str(feat),
                f"mean={r['mean']:.3f}  std={r['std']:.3f}  "
                f"min={r['min']:.3f}  max={r['max']:.3f}")

    # ── Flow stats ────────────────────────────────────────
    if "flow_id" in df.columns:
        h("FLOW STATISTICS")
        fz = df["flow_id"].value_counts()
        row("Unique flows",          f"{len(fz):,}")
        row("Max packets/flow",      f"{fz.max():,}")
        row("Mean packets/flow",     f"{fz.mean():.1f}")
        row("Median packets/flow",   f"{fz.median():.1f}")

    # ── Top IP pairs ──────────────────────────────────────
    if {"ip.src", "ip.dst"}.issubset(df.columns):
        h("TOP 10 IP PAIRS  (src → dst)")
        pairs = (
            df.groupby(["ip.src", "ip.dst"], dropna=False)
            .size()
            .sort_values(ascending=False)
            .head(10)
        )
        for (src, dst), cnt in pairs.items():
            row(f"{src} → {dst}", f"{cnt:,}")

    # ── Missing values ────────────────────────────────────
    h("MISSING VALUE REPORT  (columns with > 0 NaN)")
    miss = df.isnull().sum()
    miss = miss[miss > 0].sort_values(ascending=False)
    if miss.empty:
        lines.append("  (no missing values)")
    else:
        for col, cnt in miss.items():
            row(str(col), f"{cnt:,}  ({100*cnt/len(df):.1f}%)")

    # ── Column list ───────────────────────────────────────
    h("ALL COLUMNS IN OUTPUT CSV")
    for col in df.columns:
        lines.append(f"  • {col}")

    lines.append("")

    text = "\n".join(lines)
    with open(SUMMARY_FILE, "w") as fh:
        fh.write(text)
    print(text)
    print(f"\n📄 Summary saved → {SUMMARY_FILE}")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    t0 = time.time()

    # 1 – Extract
    if not run_extraction_script():
        print("❌ All extractions failed – aborting.")
        raise SystemExit(1)

    # 2 – Merge
    df = merge_csvs()
    if df is None:
        print("❌ No data merged – aborting.")
        raise SystemExit(1)

    # 3 – Feature engineering (includes labelling)
    df = engineer_features(df)

    # 4 – Deduplicate
    df = deduplicate(df)

    # 5 – Save
    print("\n" + "=" * 60)
    print(" STEP 5 – SAVE DATASET")
    print("=" * 60)
    save_dataset(df)

    # 6 – Summarise
    summarize_dataset(df, elapsed=time.time() - t0)
