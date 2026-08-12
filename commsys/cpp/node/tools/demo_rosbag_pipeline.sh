#!/usr/bin/env bash
# demo_rosbag_pipeline.sh -- downloads a real, external IMU sensor
# dataset and runs it through the full commsys_bag pipeline: parse ->
# publish -> record -> info -> play -> subscribe -> verify.
#
# Dataset: MotionSense (Malekzadeh et al., IoTDI'19) --
# https://github.com/mmalekzadeh/motion-sense -- real accelerometer/
# gyroscope readings from a smartphone. Used here under the repo's
# stated terms (cite the paper if you use the data yourself; see the
# source repo's README). Only one small per-trial CSV is extracted
# from the dataset's zip -- not committed to this repo, fetched fresh
# each time this script runs, since it's third-party data with its
# own citation/license terms rather than this project's own.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${1:-$SCRIPT_DIR/../../build}"
WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

BAG_CLI="$BUILD_DIR/node/commsys_bag"
CSV_PUBLISHER="$BUILD_DIR/node/csv_imu_publisher"
for bin in "$BAG_CLI" "$CSV_PUBLISHER"; do
  if [ ! -x "$bin" ]; then
    echo "missing $bin -- build the project first (./build.sh)"
    exit 1
  fi
done

echo "== downloading MotionSense sample data =="
curl -sL -o "$WORK_DIR/motion_data.zip" \
  "https://raw.githubusercontent.com/mmalekzadeh/motion-sense/master/data/A_DeviceMotion_data.zip"
unzip -p "$WORK_DIR/motion_data.zip" "A_DeviceMotion_data/dws_11/sub_1.csv" > "$WORK_DIR/sample.csv"
echo "extracted $(wc -l < "$WORK_DIR/sample.csv") rows of real IMU data"

BAG_FILE="$WORK_DIR/motionsense.bag"
rm -f /dev/shm/commsys_cpp_* 2>/dev/null || true

echo "== recording while replaying real data through Node =="
"$BAG_CLI" record -o "$BAG_FILE" --transport shm --duration 20 imu &
RECORD_PID=$!
sleep 0.5
"$CSV_PUBLISHER" "$WORK_DIR/sample.csv" --transport shm --rate 100
wait $RECORD_PID

echo
echo "== commsys_bag info =="
"$BAG_CLI" info "$BAG_FILE"

echo
echo "== playing back through Node (subscribe to 'imu' elsewhere to observe it live) =="
rm -f /dev/shm/commsys_cpp_* 2>/dev/null || true
"$BAG_CLI" play "$BAG_FILE" --transport shm --rate 10

echo
echo "== done: full pipeline (download -> parse -> publish -> record -> info -> play) demonstrated =="
echo "For exact-value verification against the source CSV, see tests/test_rosbag.cpp"
echo "and this project's own verification run (see ROSBAG_GUIDE.md)."
