"""
flatbuffer_codec.py
--------------------
High-level build/read helpers around the generated FlatBuffers code in
generated/RobotMsgs/, for the two hot-path robotics message types:

  - ImuBatch / EncoderBatch: many small fixed-layout samples batched
    into one buffer. Build cost is a handful of struct writes (no
    per-field boxing); read cost on the consumer side is zero parsing
    -- you index straight into the wire bytes.

  - LaserScan: one large float vector. `RangesAsNumpy()` returns a
    numpy array backed directly by the underlying bytes (no copy, no
    per-element Python float boxing), which is the whole efficiency
    win versus pickle/msgpack for a several-KB scan published at
    10-40Hz.

These are intentionally separate from `serialization.py`'s generic
Serializer: FlatBuffers requires a schema per message shape, so it's
not a drop-in replacement for arbitrary Python objects, only for the
specific hot-path types defined in schemas/robot_msgs.fbs.
"""

import sys
import os
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "generated"))

import flatbuffers
from RobotMsgs import ImuBatch, ImuSample, EncoderBatch, EncoderSample, LaserScan, Vec3


# ---------------------------------------------------------------- IMU --
def build_imu_batch(samples, builder: flatbuffers.Builder = None) -> bytes:
    """
    samples: iterable of dicts with keys
      timestamp_ns, accel=(ax,ay,az), gyro=(gx,gy,gz)
    """
    samples = list(samples)
    b = builder or flatbuffers.Builder(64 + 32 * len(samples))

    ImuBatch.ImuBatchStartSamplesVector(b, len(samples))
    # Structs are written directly inline into the vector, in reverse
    # order, per FlatBuffers' builder convention (it builds back-to-front).
    for s in reversed(samples):
        ax, ay, az = s["accel"]
        gx, gy, gz = s["gyro"]
        ImuSample.CreateImuSample(b, s["timestamp_ns"], ax, ay, az, gx, gy, gz)
    samples_vec = b.EndVector()

    ImuBatch.ImuBatchStart(b)
    ImuBatch.ImuBatchAddSamples(b, samples_vec)
    batch = ImuBatch.ImuBatchEnd(b)
    b.Finish(batch)
    return bytes(b.Output())


def read_imu_batch(buf: bytes):
    """Returns the generated ImuBatch accessor -- zero-copy view over
    `buf`. Caller indexes with .Samples(i) which returns a struct view
    (no allocation) for reading .TimestampNs(), .Accel().X()/.Y()/.Z(),
    .Gyro().X()/.Y()/.Z()."""
    return ImuBatch.ImuBatch.GetRootAs(buf, 0)


def iter_imu_samples(batch):
    """Yields (timestamp_ns, (ax,ay,az), (gx,gy,gz)) for every sample.
    Reuses a single Vec3 wrapper across the whole scan (the standard
    zero-allocation FlatBuffers iteration pattern) -- don't hold onto
    the yielded tuples' source objects past one iteration; the plain
    float tuples returned here are safe to keep, the underlying struct
    view is not."""
    vec = Vec3.Vec3()
    n = batch.SamplesLength()
    for i in range(n):
        s = batch.Samples(i)
        a = s.Accel(vec)
        accel = (a.X(), a.Y(), a.Z())
        g = s.Gyro(vec)
        gyro = (g.X(), g.Y(), g.Z())
        yield s.TimestampNs(), accel, gyro


# -------------------------------------------------------------- Encoder --
def build_encoder_batch(samples, builder: flatbuffers.Builder = None) -> bytes:
    """samples: iterable of dicts with timestamp_ns, left_ticks,
    right_ticks, velocity_mps."""
    samples = list(samples)
    b = builder or flatbuffers.Builder(64 + 32 * len(samples))

    EncoderBatch.EncoderBatchStartSamplesVector(b, len(samples))
    for s in reversed(samples):
        EncoderSample.CreateEncoderSample(
            b, s["timestamp_ns"], s["left_ticks"], s["right_ticks"], s["velocity_mps"]
        )
    samples_vec = b.EndVector()

    EncoderBatch.EncoderBatchStart(b)
    EncoderBatch.EncoderBatchAddSamples(b, samples_vec)
    batch = EncoderBatch.EncoderBatchEnd(b)
    b.Finish(batch)
    return bytes(b.Output())


def read_encoder_batch(buf: bytes):
    return EncoderBatch.EncoderBatch.GetRootAs(buf, 0)


def iter_encoder_samples(batch):
    """Yields (timestamp_ns, left_ticks, right_ticks, velocity_mps)
    for every sample; encoder structs have no nested struct fields so
    no wrapper object reuse is needed here."""
    n = batch.SamplesLength()
    for i in range(n):
        s = batch.Samples(i)
        yield s.TimestampNs(), s.LeftTicks(), s.RightTicks(), s.VelocityMps()


# ------------------------------------------------------------- LaserScan --
def build_laser_scan(timestamp_ns: int, angle_min: float, angle_max: float,
                      angle_increment: float, range_min: float, range_max: float,
                      ranges, intensities=None,
                      builder: flatbuffers.Builder = None) -> bytes:
    """
    `ranges` / `intensities`: any sequence of floats (list or numpy
    array). Uses CreateNumpyVector when given a numpy float32 array for
    a fast bulk memcpy into the builder instead of a per-element loop.
    """
    ranges = np.asarray(ranges, dtype=np.float32)
    b = builder or flatbuffers.Builder(64 + 4 * len(ranges) +
                                        (4 * len(intensities) if intensities is not None else 0))

    intensities_vec = None
    if intensities is not None:
        intensities = np.asarray(intensities, dtype=np.float32)
        intensities_vec = b.CreateNumpyVector(intensities)

    ranges_vec = b.CreateNumpyVector(ranges)

    LaserScan.LaserScanStart(b)
    LaserScan.LaserScanAddTimestampNs(b, timestamp_ns)
    LaserScan.LaserScanAddAngleMin(b, angle_min)
    LaserScan.LaserScanAddAngleMax(b, angle_max)
    LaserScan.LaserScanAddAngleIncrement(b, angle_increment)
    LaserScan.LaserScanAddRangeMin(b, range_min)
    LaserScan.LaserScanAddRangeMax(b, range_max)
    LaserScan.LaserScanAddRanges(b, ranges_vec)
    if intensities_vec is not None:
        LaserScan.LaserScanAddIntensities(b, intensities_vec)
    scan = LaserScan.LaserScanEnd(b)
    b.Finish(scan)
    return bytes(b.Output())


def read_laser_scan(buf: bytes):
    """Returns the generated LaserScan accessor. Use .RangesAsNumpy()
    for a zero-copy numpy view of the range array (backed directly by
    `buf` -- no allocation, no per-element parsing)."""
    return LaserScan.LaserScan.GetRootAs(buf, 0)
