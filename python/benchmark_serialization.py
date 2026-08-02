"""
benchmark_serialization.py
----------------------------
Compares pickle / msgpack / FlatBuffers on the two robotics workload
shapes this system targets:

  1. IMU/encoder batches: small (~20-40 samples), published at a rate
     that implies serializing thousands of these per second. What
     matters here is *per-call* CPU overhead, not payload size.

  2. LaserScan: one big float array (1080-2000 points, matching
     common 2D LiDAR specs), published at 10-40Hz. What matters here
     is bytes moved and whether reading requires materializing the
     full array before you can use any of it.

Run: python3 benchmark_serialization.py
"""

import time
import pickle
import struct
import statistics
import numpy as np

try:
    import msgpack
    HAS_MSGPACK = True
except ImportError:
    HAS_MSGPACK = False

from flatbuffer_codec import (
    build_imu_batch, read_imu_batch, iter_imu_samples,
    build_laser_scan, read_laser_scan,
)


def timed(fn, iters, warmup=50):
    for _ in range(warmup):
        fn()
    samples = []
    for _ in range(iters):
        t0 = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - t0)
    samples.sort()
    return {
        "mean_us": statistics.mean(samples) * 1e6,
        "p50_us": samples[len(samples) // 2] * 1e6,
        "p99_us": samples[int(len(samples) * 0.99)] * 1e6,
    }


def fmt_row(name, stats, size_bytes):
    return (f"  {name:<28} mean={stats['mean_us']:8.2f}us  "
            f"p50={stats['p50_us']:8.2f}us  p99={stats['p99_us']:8.2f}us  "
            f"size={size_bytes:>7d}B")


# --------------------------------------------------------------------- IMU --
def bench_imu(n_samples=20, iters=2000):
    print(f"\n=== IMU batch: {n_samples} samples/msg "
          f"(e.g. 1kHz IMU batched every {n_samples}ms) ===")
    samples = [{"timestamp_ns": i, "accel": (0.1, 0.2, 9.81), "gyro": (0.01, 0.02, 0.03)}
               for i in range(n_samples)]
    samples_pk = [{"timestamp_ns": i, "accel": [0.1, 0.2, 9.81], "gyro": [0.01, 0.02, 0.03]}
                  for i in range(n_samples)]

    # -- pickle --
    pk_bytes = pickle.dumps(samples_pk, protocol=pickle.HIGHEST_PROTOCOL)
    s = timed(lambda: pickle.dumps(samples_pk, protocol=pickle.HIGHEST_PROTOCOL), iters)
    print(fmt_row("pickle serialize", s, len(pk_bytes)))
    s = timed(lambda: pickle.loads(pk_bytes), iters)
    print(fmt_row("pickle deserialize", s, len(pk_bytes)))

    # -- msgpack --
    if HAS_MSGPACK:
        mp_bytes = msgpack.packb(samples_pk, use_bin_type=True)
        s = timed(lambda: msgpack.packb(samples_pk, use_bin_type=True), iters)
        print(fmt_row("msgpack serialize", s, len(mp_bytes)))
        s = timed(lambda: msgpack.unpackb(mp_bytes, raw=False), iters)
        print(fmt_row("msgpack deserialize", s, len(mp_bytes)))

    # -- flatbuffers --
    fb_bytes = build_imu_batch(samples)
    s = timed(lambda: build_imu_batch(samples), iters)
    print(fmt_row("flatbuffers build", s, len(fb_bytes)))

    def fb_read_and_sum():
        batch = read_imu_batch(fb_bytes)
        total = 0.0
        for ts, accel, gyro in iter_imu_samples(batch):
            total += accel[2]
        return total
    s = timed(fb_read_and_sum, iters)
    print(fmt_row("flatbuffers read+sum (zero-copy)", s, len(fb_bytes)))

    # -- raw struct.pack: the "even flatter than FlatBuffers" option --
    # FlatBuffers' Python *builder* does real per-field work (Prep/Pad/
    # Prepend calls, each a Python function call) to stay
    # schema-flexible and support vtables for the table wrapper. A
    # fixed-shape batch of identical structs doesn't need any of that
    # -- struct.pack can write the same bytes with one C call.
    FMT = "<Qffffff"  # matches ImuSample's on-wire layout exactly
    raw_bytes = b"".join(struct.pack(FMT, s["timestamp_ns"], *s["accel"], *s["gyro"])
                          for s in samples)

    def raw_pack():
        return b"".join(struct.pack(FMT, s["timestamp_ns"], *s["accel"], *s["gyro"])
                         for s in samples)
    s = timed(raw_pack, iters)
    print(fmt_row("raw struct.pack (no schema)", s, len(raw_bytes)))

    def raw_unpack_and_sum():
        total = 0.0
        step = struct.calcsize(FMT)
        for off in range(0, len(raw_bytes), step):
            total += struct.unpack_from(FMT, raw_bytes, off)[3]  # accel.z
        return total
    s = timed(raw_unpack_and_sum, iters)
    print(fmt_row("raw struct.unpack_from+sum", s, len(raw_bytes)))


# --------------------------------------------------------------- LaserScan --
def bench_laser_scan(n_points=1080, iters=500):
    print(f"\n=== LaserScan: {n_points} points/scan "
          f"(typical 2D LiDAR sweep width) ===")
    ranges = np.random.uniform(0.05, 25.0, size=n_points).astype(np.float32)
    ranges_list = ranges.tolist()
    scan_dict = {"timestamp_ns": 1, "angle_min": -3.14, "angle_max": 3.14,
                 "angle_increment": 0.0058, "range_min": 0.05, "range_max": 30.0,
                 "ranges": ranges_list}

    # -- pickle --
    pk_bytes = pickle.dumps(scan_dict, protocol=pickle.HIGHEST_PROTOCOL)
    s = timed(lambda: pickle.dumps(scan_dict, protocol=pickle.HIGHEST_PROTOCOL), iters)
    print(fmt_row("pickle serialize", s, len(pk_bytes)))
    s = timed(lambda: pickle.loads(pk_bytes), iters)
    print(fmt_row("pickle deserialize (full list)", s, len(pk_bytes)))

    # -- msgpack --
    if HAS_MSGPACK:
        mp_bytes = msgpack.packb(scan_dict, use_bin_type=True)
        s = timed(lambda: msgpack.packb(scan_dict, use_bin_type=True), iters)
        print(fmt_row("msgpack serialize", s, len(mp_bytes)))
        s = timed(lambda: msgpack.unpackb(mp_bytes, raw=False), iters)
        print(fmt_row("msgpack deserialize (full list)", s, len(mp_bytes)))

    # -- flatbuffers: build from numpy array (bulk memcpy path) --
    fb_bytes = build_laser_scan(1, -3.14, 3.14, 0.0058, 0.05, 30.0, ranges)
    s = timed(lambda: build_laser_scan(1, -3.14, 3.14, 0.0058, 0.05, 30.0, ranges), iters)
    print(fmt_row("flatbuffers build (numpy path)", s, len(fb_bytes)))

    # "read" here means get a usable numpy view -- no full-array
    # deserialization, just pointer + length + dtype bookkeeping.
    s = timed(lambda: read_laser_scan(fb_bytes).RangesAsNumpy(), iters)
    print(fmt_row("flatbuffers read (zero-copy view)", s, len(fb_bytes)))

    # fairer apples-to-apples: touch every element (sum), since pickle/
    # msgpack's cost above already includes materializing every element
    def fb_read_and_sum():
        arr = read_laser_scan(fb_bytes).RangesAsNumpy()
        return float(arr.sum())
    s = timed(fb_read_and_sum, iters)
    print(fmt_row("flatbuffers read+sum(all elems)", s, len(fb_bytes)))

    def pk_read_and_sum():
        d = pickle.loads(pk_bytes)
        return sum(d["ranges"])
    s = timed(pk_read_and_sum, iters)
    print(fmt_row("pickle deserialize+sum", s, len(pk_bytes)))


def bench_partial_access_pattern():
    """The scenario where FlatBuffers' advantage is largest: the
    consumer only needs a few values out of a big scan (e.g. an
    obstacle-avoidance check on 5 forward-facing beams), not the whole
    array. Pickle/msgpack must pay for the whole array regardless."""
    print("\n=== Partial access: read only 5 of 1080 range values ===")
    n_points = 1080
    ranges = np.random.uniform(0.05, 25.0, size=n_points).astype(np.float32)
    scan_dict = {"ranges": ranges.tolist()}
    pk_bytes = pickle.dumps(scan_dict, protocol=pickle.HIGHEST_PROTOCOL)
    fb_bytes = build_laser_scan(0, 0, 0, 0, 0, 0, ranges)
    mid = n_points // 2
    idxs = [mid - 2, mid - 1, mid, mid + 1, mid + 2]

    def pk_partial():
        d = pickle.loads(pk_bytes)  # forced to build the whole list
        return [d["ranges"][i] for i in idxs]

    def fb_partial():
        scan = read_laser_scan(fb_bytes)
        return [scan.Ranges(i) for i in idxs]  # no full-array materialization

    iters = 2000
    s = timed(pk_partial, iters)
    print(fmt_row("pickle (must build full list)", s, len(pk_bytes)))
    s = timed(fb_partial, iters)
    print(fmt_row("flatbuffers (direct index, no copy)", s, len(fb_bytes)))


if __name__ == "__main__":
    print("commsys serialization benchmark")
    print("=" * 70)
    bench_imu(n_samples=20, iters=2000)
    bench_imu(n_samples=1, iters=3000)   # unbatched, worst case per-message overhead
    bench_laser_scan(n_points=1080, iters=500)
    bench_laser_scan(n_points=2000, iters=300)
    bench_partial_access_pattern()
