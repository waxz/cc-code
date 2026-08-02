"""
demo_ros_like.py
------------------
A small robot "graph" of five independent OS processes, each a real
Node (discovery.py + node.py), to exercise this system the way it'd
actually be used -- not in-process asyncio tasks pretending to be
separate nodes, but genuinely separate processes finding each other
at runtime with no hardcoded addresses.

Graph:
  imu_node    (publishes "imu",  200Hz, small FlatBuffers batches)
  lidar_node  (publishes "scan", 20Hz,  large FlatBuffers LaserScan)
  controller  (subscribes "imu"          via shared memory -- same host,
                                              low-latency control loop)
  logger      (subscribes "imu" + "scan" via UDP -- simulates a separate
                                              logging computer over network)
  mapper      (subscribes "scan"         via shared memory)

This deliberately mixes transports on the SAME topic ("imu" reaches
controller over shared memory and logger over UDP at the same time)
to prove the per-link transport negotiation actually works, not just
in isolation.

Each subscriber process reports message count, drop count, and
latency/bandwidth stats back to this parent process via a
multiprocessing.Queue once the run completes.
"""

import asyncio
import multiprocessing as mp
import statistics
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from node import Node
from flatbuffer_codec import build_imu_batch, read_imu_batch, build_laser_scan, read_laser_scan
import numpy as np

RUN_SECONDS = 6.0
IMU_RATE_HZ = 500
IMU_BATCH_SIZE = 1       # publish every sample individually -> true 500Hz message rate
LIDAR_RATE_HZ = 20
LIDAR_POINTS = 2000


def imu_producer(registry_barrier, discovery_lock):
    async def run():
        node = Node("imu_node", discovery_lock=discovery_lock)
        await node.start()
        node.advertise("imu")
        registry_barrier.wait()  # let all nodes register before publishing starts
        await asyncio.sleep(1.0)  # give discovery time to wire up links

        period = IMU_BATCH_SIZE / IMU_RATE_HZ
        t_end = time.monotonic() + RUN_SECONDS
        i = 0
        while time.monotonic() < t_end:
            samples = [{"timestamp_ns": time.time_ns(), "accel": (0.01 * i, 0.0, 9.81),
                        "gyro": (0.0, 0.0, 0.001 * i)} for _ in range(IMU_BATCH_SIZE)]
            buf = build_imu_batch(samples)
            await node.publish("imu", buf)
            i += 1
            await asyncio.sleep(period)
        await asyncio.sleep(0.3)
        await node.stop()

    asyncio.run(run())


def lidar_producer(registry_barrier, discovery_lock):
    async def run():
        node = Node("lidar_node", discovery_lock=discovery_lock)
        await node.start()
        node.advertise("scan")
        registry_barrier.wait()
        await asyncio.sleep(1.0)

        rng = np.random.default_rng(0)
        period = 1.0 / LIDAR_RATE_HZ
        t_end = time.monotonic() + RUN_SECONDS
        while time.monotonic() < t_end:
            ranges = rng.uniform(0.05, 25.0, size=LIDAR_POINTS).astype(np.float32)
            buf = build_laser_scan(time.time_ns(), -3.14, 3.14, 0.0058, 0.05, 30.0, ranges)
            await node.publish("scan", buf)
            await asyncio.sleep(period)
        await asyncio.sleep(0.3)
        await node.stop()

    asyncio.run(run())


def subscriber(node_id: str, topics: list, force_transport: str,
                registry_barrier, results_queue: mp.Queue, discovery_lock):
    async def run():
        node = Node(node_id, force_transport=force_transport, discovery_lock=discovery_lock)
        await node.start()

        latencies_by_topic = {t: [] for t in topics}
        bytes_by_topic = {t: 0 for t in topics}
        counts_by_topic = {t: 0 for t in topics}

        def make_cb(topic):
            def cb(payload: bytes):
                counts_by_topic[topic] += 1
                bytes_by_topic[topic] += len(payload)
            return cb

        for t in topics:
            node.subscribe(t, make_cb(t))

        registry_barrier.wait()
        t_start = time.monotonic()
        await asyncio.sleep(1.0 + RUN_SECONDS + 0.5)

        # node.stats[topic].latencies_ns is populated by node.py's own
        # dispatch path (send_ns embedded in the wire envelope), which
        # is more precise than anything we could measure from the
        # callback alone -- pull the real numbers from there.
        report = {}
        for t in topics:
            st = node.stats[t]
            lat_ms = [ns / 1e6 for ns in st.latencies_ns]
            report[t] = {
                "count": st.count,
                "drops": st.drops,
                "bytes": st.bytes_total,
                "mean_latency_ms": statistics.mean(lat_ms) if lat_ms else None,
                "p50_latency_ms": statistics.median(lat_ms) if lat_ms else None,
                "p99_latency_ms": (sorted(lat_ms)[int(len(lat_ms) * 0.99)]
                                   if len(lat_ms) > 1 else (lat_ms[0] if lat_ms else None)),
                "duration_s": RUN_SECONDS,
            }
        results_queue.put((node_id, force_transport, report))
        await node.stop()

    asyncio.run(run())


def fmt_bw(bytes_total, seconds):
    mbps = (bytes_total / seconds) / 1e6
    return f"{mbps:.2f} MB/s"


def main():
    mp.set_start_method("fork")
    barrier = mp.Barrier(5)  # imu, lidar, controller, logger, mapper
    results_q = mp.Queue()
    discovery_lock = mp.Lock()  # protects discovery slot-claim races across all nodes

    procs = [
        mp.Process(target=imu_producer, args=(barrier, discovery_lock), name="imu_node"),
        mp.Process(target=lidar_producer, args=(barrier, discovery_lock), name="lidar_node"),
        mp.Process(target=subscriber, args=("controller", ["imu"], "shm", barrier, results_q, discovery_lock),
                   name="controller"),
        mp.Process(target=subscriber, args=("logger", ["imu", "scan"], "udp", barrier, results_q, discovery_lock),
                   name="logger"),
        mp.Process(target=subscriber, args=("mapper", ["scan"], "shm", barrier, results_q, discovery_lock),
                   name="mapper"),
    ]

    print(f"Starting {len(procs)} node processes for {RUN_SECONDS:.0f}s run...")
    print("  imu_node   -> publishes 'imu'  @ ~%dHz (batches of %d)" % (
        IMU_RATE_HZ // IMU_BATCH_SIZE * IMU_BATCH_SIZE // IMU_BATCH_SIZE, IMU_BATCH_SIZE))
    print(f"  lidar_node -> publishes 'scan' @ {LIDAR_RATE_HZ}Hz ({LIDAR_POINTS} pts/scan)")
    print("  controller -> subscribes 'imu'          [forced shm]")
    print("  logger     -> subscribes 'imu' + 'scan'  [forced udp]")
    print("  mapper     -> subscribes 'scan'          [forced shm]")
    print()

    for p in procs:
        p.start()

    collected = {}
    n_subscribers = 3
    for _ in range(n_subscribers):
        node_id, transport, report = results_q.get(timeout=RUN_SECONDS + 15)
        collected[node_id] = (transport, report)

    for p in procs:
        p.join(timeout=10)
        if p.is_alive():
            p.terminate()

    # The discovery registry is intentionally long-lived (any future
    # node could reuse it, so no single node unlinks it on exit) --
    # but this demo script knows the whole run is over, so it's the
    # right place to actually remove it.
    try:
        from multiprocessing import shared_memory
        shared_memory.SharedMemory(name="/commsys_discovery").unlink()
    except FileNotFoundError:
        pass

    print("=" * 78)
    print(f"{'node':<12}{'topic':<8}{'transport':<10}{'msgs':>8}{'drops':>7}"
          f"{'bandwidth':>14}{'mean lat':>12}{'p99 lat':>12}")
    print("-" * 78)
    for node_id, (transport, report) in collected.items():
        for topic, stats in report.items():
            bw = fmt_bw(stats["bytes"], stats["duration_s"])
            mean_lat = f"{stats['mean_latency_ms']:.3f}ms" if stats["mean_latency_ms"] is not None else "n/a"
            p99_lat = f"{stats['p99_latency_ms']:.3f}ms" if stats["p99_latency_ms"] is not None else "n/a"
            print(f"{node_id:<12}{topic:<8}{transport:<10}{stats['count']:>8}{stats['drops']:>7}"
                  f"{bw:>14}{mean_lat:>12}{p99_lat:>12}")
    print("=" * 78)


if __name__ == "__main__":
    main()
