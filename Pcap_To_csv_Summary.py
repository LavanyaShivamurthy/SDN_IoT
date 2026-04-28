import os
import subprocess
import pandas as pd
import time

# === CONFIGURATION ===
BASE_DIR = "/home/ictlab7/Documents/Learning_Mininet"
PCAP_DIR = os.path.join(BASE_DIR, "pcap_captures")
CSV_DIR = os.path.join(BASE_DIR, "csvLSTM")   # ✅ FIXED
EXTRACT_SCRIPT = os.path.join(BASE_DIR, "scripts/extract_pcap_to_csv_labeled_LSTM.sh")

OUTPUT_FILE = os.path.join(CSV_DIR, "all_labeled_data_clean.csv")
SUMMARY_FILE = os.path.join(CSV_DIR, "dataset_summary.txt")

DUPLICATE_KEYS = [
    "frame.time_relative", "ip.src", "ip.dst",
    "tcp.srcport", "tcp.dstport", "mqtt.topic", "mqtt.msgtype", "mqtt.msg"
]

# Ensure output directory exists
os.makedirs(CSV_DIR, exist_ok=True)


# =====================================================
# STEP 1: RUN EXTRACTION
# =====================================================
def run_extraction_script():
    print(f"🚀 Running extraction script on PCAP directory: {PCAP_DIR}")

    if not os.path.exists(EXTRACT_SCRIPT):
        print(f"❌ Script not found at {EXTRACT_SCRIPT}")
        return False

    if not os.path.exists(PCAP_DIR):
        print(f"❌ PCAP directory not found: {PCAP_DIR}")
        return False

    pcap_files = sorted([
        os.path.join(PCAP_DIR, f)
        for f in os.listdir(PCAP_DIR)
        if f.endswith(".pcap") or f.endswith(".pcapng")
    ])

    if not pcap_files:
        print(f"❌ No PCAP files found in {PCAP_DIR}")
        return False

    print(f"📦 Found {len(pcap_files)} PCAP files")

    for pcap in pcap_files:
        print(f"\n🔄 Processing PCAP: {os.path.basename(pcap)}")

        try:
            result = subprocess.run(
                ["bash", EXTRACT_SCRIPT, pcap],   # ✅ FIXED
                capture_output=True,
                text=True,
                cwd=BASE_DIR
            )

            print(result.stdout)

            if result.stderr.strip():
                print("⚠️ Script warnings/errors:\n", result.stderr)

            if result.returncode != 0:
                print(f"❌ Script failed for {pcap}, skipping...")
                continue   # ✅ FIXED

        except Exception as e:
            print(f"❌ Failed to process {pcap}: {e}")
            continue

    print("\n✅ Extraction completed for all PCAP files.")
    return True


# =====================================================
# STEP 2: MERGE CSVs
# =====================================================
def merge_and_clean_csvs(folder):
    print(f"📂 Searching labeled CSVs in: {folder}")

    all_files = [
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.endswith("_labeled.csv")
    ]

    if not all_files:
        print(f"❌ No labeled CSV files found in {folder}")
        return None

    dataframes = []

    for file in all_files:
        print(f"📦 Loading {os.path.basename(file)} ...")
        try:
            df = pd.read_csv(file)
            df["source_file"] = os.path.basename(file)
            dataframes.append(df)
        except Exception as e:
            print(f"⚠️ Skipping {file} due to error: {e}")

    print("🔄 Merging all CSVs ...")
    merged_df = pd.concat(dataframes, ignore_index=True)

    # Remove duplicates
    existing_cols = [col for col in DUPLICATE_KEYS if col in merged_df.columns]

    if existing_cols:
        before = len(merged_df)
        merged_df.drop_duplicates(subset=existing_cols, inplace=True)
        after = len(merged_df)
        print(f"🧹 Removed {before - after} duplicates")
    else:
        print("⚠️ No duplicate columns found")

    print(f"💾 Saving merged CSV to: {OUTPUT_FILE}")
    merged_df.to_csv(OUTPUT_FILE, index=False)

    print(f"✅ Final rows: {len(merged_df)}")
    return merged_df


# =====================================================
# STEP 3: SUMMARY
# =====================================================
def summarize_dataset(df, start_time):
    print("📊 Generating dataset summary...")

    elapsed_time = time.time() - start_time

    summary_lines = [
        "========== DATASET SUMMARY ==========",
        f"📁 Output CSV File : {OUTPUT_FILE}",
        f"🕒 Total Processing Time : {elapsed_time:.2f} seconds",
        f"📦 Total Packets : {len(df)}",
        f"📐 Total Columns : {len(df.columns)}",
        ""
    ]

    with open(SUMMARY_FILE, "w") as f:
        f.write("\n".join(summary_lines))

    print("\n".join(summary_lines))


# =====================================================
# MAIN
# =====================================================
if __name__ == "__main__":
    start_time = time.time()

    if run_extraction_script():
        merged_df = merge_and_clean_csvs(CSV_DIR)

        if merged_df is not None:
            summarize_dataset(merged_df, start_time)
    else:
        print("❌ Extraction failed; skipping merge and summary.")
