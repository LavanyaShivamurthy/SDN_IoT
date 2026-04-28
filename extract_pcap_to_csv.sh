#!/bin/bash

# =====================================================
# PCAP → CSV EXTRACTION  |  ICU MQTT CLASSIFICATION
# Classes:
#   1 → Emergency & Important       (ecg, pulse_oximeter, bp, fire)
#   2 → Emergency but Not Important (emg, airflow, barometer, smoke)
#   3 → Not Emergency but Important (infusion_pump, glucometer, gsr)
#   4 → Not Emergency & Not Important (humidity, temperature, co)
# =====================================================

if [ $# -ne 1 ]; then
    echo "Usage: $0 <pcap_file>"
    exit 1
fi

PCAP="$1"
OUT_DIR="csvLSTM"

# ── Preflight checks ─────────────────────────────────
if [ ! -f "$PCAP" ]; then
    echo "❌ ERROR: File not found: $PCAP"
    exit 1
fi

if ! command -v tshark &>/dev/null; then
    echo "❌ ERROR: tshark not found. Install wireshark-cli / tshark."
    exit 1
fi

mkdir -p "$OUT_DIR"

BASENAME=$(basename "$PCAP")
BASENAME="${BASENAME%.*}"
CSV_FILE="$OUT_DIR/${BASENAME}_rawData.csv"

echo "=============================================="
echo " ICU MQTT PCAP EXTRACTION"
echo " PCAP   : $PCAP"
echo " OUTPUT : $CSV_FILE"
echo "=============================================="
echo

# ── Quick packet audit ────────────────────────────────
TOTAL_PKTS=$(tshark -r "$PCAP" 2>/dev/null | wc -l)
MQTT_PKTS=$(tshark  -r "$PCAP" -Y mqtt 2>/dev/null | wc -l)
echo "[DEBUG] Total packets : $TOTAL_PKTS"
echo "[DEBUG] MQTT  packets : $MQTT_PKTS"
echo

# ── Extract fields ────────────────────────────────────
# All packets kept (not only MQTT) so the model sees full flow context.
# MQTT-specific fields will be empty for non-MQTT rows (become NaN).
echo "[1/3] Extracting fields..."

tshark -r "$PCAP" \
    -d tcp.port==1883,mqtt \
    -T fields \
    \
    -e frame.number                     \
    -e frame.time_epoch                 \
    -e frame.time_delta                 \
    -e frame.time_relative              \
    -e frame.len                        \
    -e frame.cap_len                    \
    -e frame.protocols                  \
    \
    -e ip.src                           \
    -e ip.dst                           \
    -e ip.proto                         \
    -e ip.len                           \
    -e ip.ttl                           \
    -e ip.flags                         \
    \
    -e tcp.srcport                      \
    -e tcp.dstport                      \
    -e tcp.len                          \
    -e tcp.flags                        \
    -e tcp.window_size                  \
    -e tcp.seq                          \
    -e tcp.ack                          \
    -e tcp.hdr_len                      \
    -e tcp.analysis.retransmission      \
    -e tcp.analysis.duplicate_ack       \
    \
    -e udp.srcport                      \
    -e udp.dstport                      \
    -e udp.length                       \
    \
    -e mqtt.clientid                    \
    -e mqtt.topic                       \
    -e mqtt.qos                         \
    -e mqtt.msgtype                     \
    -e mqtt.len                         \
    -e mqtt.retain                      \
    -e mqtt.dupflag                     \
    -e mqtt.msg                         \
    \
    -E header=y     \
    -E separator=,  \
    -E quote=d      \
    -E occurrence=f \
    2>/dev/null     \
    > "$CSV_FILE"

# ── Validate ──────────────────────────────────────────
echo "[2/3] Validating..."
ROWS=$(wc -l < "$CSV_FILE")
echo "  Total rows (incl. header): $ROWS"

if [ "$ROWS" -le 1 ]; then
    echo "❌ CSV is empty for $PCAP – check tshark can read the file."
    rm -f "$CSV_FILE"
    exit 1
fi
echo "  ✔ $CSV_FILE"
echo

# ── MQTT topic sample ─────────────────────────────────
echo "[3/3] MQTT Topic sample (this file)"
TOPIC_COL=$(head -1 "$CSV_FILE" \
    | tr ',' '\n'               \
    | grep -n "^\"mqtt.topic\"$"\
    | cut -d: -f1)

if [ -n "$TOPIC_COL" ]; then
    cut -d',' -f"$TOPIC_COL" "$CSV_FILE" \
        | tail -n +2                      \
        | tr -d '"'                       \
        | grep -v '^$'                    \
        | sort                            \
        | uniq -c                         \
        | sort -rn                        \
        | head -20
else
    echo "  (mqtt.topic column not found in header)"
fi

echo
echo "=============================================="
echo " DONE: $CSV_FILE"
echo "=============================================="
