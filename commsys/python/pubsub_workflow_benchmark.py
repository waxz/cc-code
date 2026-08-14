#!/usr/bin/env python3
"""pubsub_workflow_benchmark.py -- same realistic multi-topic pub/sub
workflow as the C++ version (cpp/node/bench/pubsub_workflow_benchmark.cpp),
for direct comparison. One publisher process, one subscriber process,
three concurrent topics at realistic robot sensor rates (imu=100Hz,
encoder=50Hz, pose=20Hz), fixed duration. Same message shapes (as
struct.pack layouts matching commsys::msg::Imu/Encoder/Pose2D's field
order) and same measurement methodology (per-message latency in ms,
p50/p99/max) as the C++ side and as benchmark_report.py, so the
numbers are directly comparable across all three.

See PUBSUB_WORKFLOW_COMPARISON.md for the actual comparison.
"""
import asyncio
import multiprocessing as mp
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from node import Node  # noqa: E402

# Struct layouts matching commsys::msg::{Imu,Encoder,Pose2D} field
# order exactly, so both languages are moving equivalently-sized,
# equivalently-shaped payloads over the wire.
IMU_FMT = "<Qffffff"       # timestamp_ns, ax,ay,az, gx,gy,gz
ENCODER_FMT = "<Qqqf"      # timestamp_ns, left_ticks, right_ticks, velocity_mps
POSE_FMT = "<Qfff"         # timestamp_ns, x, y, theta


def percentiles(latencies_ms):
    if not latencies_ms:
        return 0.0, 0.0, 0.0, 0.0
    v = sorted(latencies_ms)
    n = len(v)
    mean = sum(v) / n
    p50 = v[n // 2]
    p99 = v[int(n * 0.99)]
    return mean, p50, p99, v[-1]


def subscriber_proc(transport, duration_s, conn, discovery_lock):
    async def run():
        node = Node("workflow_sub", force_transport=transport, discovery_lock=discovery_lock)
        await node.start()
        node.subscribe("imu", lambda p: None)
        node.subscribe("encoder", lambda p: None)
        node.subscribe("pose", lambda p: None)
        await asyncio.sleep(duration_s + 2.0)

        results = {}
        for topic in ("imu", "encoder", "pose"):
            st = node.stats[topic]
            latencies_ms = [ns / 1e6 for ns in st.latencies_ns]
            mean, p50, p99, mx = percentiles(latencies_ms)
            results[topic] = dict(received=st.count, drops=st.drops, mean_ms=mean, p50_ms=p50, p99_ms=p99, max_ms=mx)
        await node.stop()
        conn.send(results)
        conn.close()

    asyncio.run(run())


async def publisher_main(transport, duration_s, discovery_lock):
    node = Node("workflow_pub", force_transport=transport, discovery_lock=discovery_lock)
    await node.start()
    node.advertise("imu")
    node.advertise("encoder")
    node.advertise("pose")
    await asyncio.sleep(0.8)  # let discovery settle, matching the C++ side

    t_end = time.monotonic() + duration_s
    imu_sent = enc_sent = pose_sent = 0
    imu_period, enc_period, pose_period = 1.0 / 100, 1.0 / 50, 1.0 / 20
    next_imu = next_enc = next_pose = time.monotonic()

    while time.monotonic() < t_end:
        now = time.monotonic()
        if now >= next_imu:
            payload = struct.pack(IMU_FMT, imu_sent, 0.1, 0.0, 9.81, 0.0, 0.0, 0.0)
            await node.publish("imu", payload)
            imu_sent += 1
            next_imu += imu_period
        if now >= next_enc:
            payload = struct.pack(ENCODER_FMT, enc_sent, enc_sent * 10, enc_sent * 10, 0.5)
            await node.publish("encoder", payload)
            enc_sent += 1
            next_enc += enc_period
        if now >= next_pose:
            payload = struct.pack(POSE_FMT, pose_sent, pose_sent * 0.01, 0.0, 0.0)
            await node.publish("pose", payload)
            pose_sent += 1
            next_pose += pose_period
        await asyncio.sleep(0)  # yield to the event loop -- same reasoning as spin_once(0) on the C++ side

    await asyncio.sleep(1.0)
    await node.stop()
    return dict(imu=imu_sent, encoder=enc_sent, pose=pose_sent)


def main():
    transport = sys.argv[1] if len(sys.argv) > 1 else "shm"
    duration = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0

    print(f"# commsys Python pub/sub workflow benchmark (transport={transport}, duration={duration:.1f}s)\n")
    print("Workflow: one publisher, one subscriber, three concurrent topics at")
    print("realistic robot sensor rates (imu=100Hz, encoder=50Hz, pose=20Hz).\n")

    discovery_lock = mp.Lock()  # protects discovery slot-claim races across both processes
    parent_conn, child_conn = mp.Pipe()
    p = mp.Process(target=subscriber_proc, args=(transport, duration, child_conn, discovery_lock))
    p.start()
    time.sleep(0.3)
    sent_counts = asyncio.run(publisher_main(transport, duration, discovery_lock))
    results = parent_conn.recv()
    p.join()

    print("| topic      |   sent | recv'd |  drops | mean(ms) |  p99(ms) |  max(ms) |")
    print("|------------|--------|--------|--------|----------|----------|----------|")
    for topic in ("imu", "encoder", "pose"):
        r = results[topic]
        print(f"| {topic:<10} | {sent_counts[topic]:6d} | {r['received']:6d} | {r['drops']:6d} | "
              f"{r['mean_ms']:8.4f} | {r['p99_ms']:8.4f} | {r['max_ms']:8.4f} |")


if __name__ == "__main__":
    main()
