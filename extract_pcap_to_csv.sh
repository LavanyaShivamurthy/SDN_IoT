#!/bin/bash

# =====================================================
# FULL PCAP EXTRACTION + MQTT VALIDATION (LSTM  and CNN row packet )
# =====================================================

if [ $# -ne 1 ]; then
    echo "Usage: $0 <pcap_file>"
    exit 1
fi

PCAP="$1"
OUT_DIR="csvLSTM"

# Create output directory
mkdir -p "$OUT_DIR"

# Extract base filename safely (.pcap or .pcapng)
BASENAME=$(basename "$PCAP")
BASENAME="${BASENAME%.*}"

CSV_FILE="$OUT_DIR/${BASENAME}_rawData.csv"

echo "=============================================="
echo " FULL PCAP EXTRACTION & MQTT VALIDATION"
echo " PCAP: $PCAP"
echo " OUTPUT: $CSV_FILE"
echo "=============================================="
echo

# -----------------------------------------------------
# DEBUG: Check MQTT presence
# -----------------------------------------------------
echo "[DEBUG] MQTT packet count:"
tshark -r "$PCAP" -Y mqtt | wc -l
echo

# -----------------------------------------------------
# 1. EXTRACT ALL PACKETS
# -----------------------------------------------------
echo "[1/3] Extracting packets..."

tshark -r "$PCAP" \
        -d tcp.port==1883,mqtt \
	-T fields \
	-e frame.number \
	-e frame.time_epoch \
	-e frame.time_delta \
	-e frame.len \
	-e ip.src \
	-e ip.dst \
	-e ip.proto \
	-e ip.len \
	-e tcp.srcport \
	-e tcp.dstport \
	-e tcp.len \
	-e tcp.flags \
	-e tcp.window_size \
	-e tcp.seq \
	-e tcp.ack \
	-e udp.srcport \
	-e udp.dstport \
	-e mqtt.clientid \
	-e mqtt.topic \
	-e mqtt.qos \
	-e mqtt.msgtype \
	-e frame.protocols \
	-E header=y \
	-E separator=, \
	-E quote=d \
	-E occurrence=f \
	> "$CSV_FILE"

# -----------------------------------------------------
# 2. VALIDATE OUTPUT
# -----------------------------------------------------
echo "[2/3] Validating CSV..."

ROWS=$(wc -l < "$CSV_FILE")
echo "Total rows: $ROWS"

if [ "$ROWS" -le 1 ]; then
    echo "❌ ERROR: CSV is empty for $PCAP"
    rm -f "$CSV_FILE"
    exit 1
else
    echo "✔ CSV successfully created"
fi
echo

# -----------------------------------------------------
# 3. QUICK MQTT SUMMARY
# -----------------------------------------------------
echo "[3/3] MQTT Topic Distribution (sample)"

cut -d',' -f13 "$CSV_FILE" | tail -n +2 | grep -v '^$' | sort | uniq -c | head

echo
echo "=============================================="
echo " EXTRACTION COMPLETE"
echo "=============================================="
