"""
tests/test_flatbuffer_codec.py
--------------------------------
Unit tests for flatbuffer_codec.py covering the robotics message
types: IMU/encoder batches (small, high-frequency) and laser scans
(large, lower-frequency). Includes edge cases specific to those
workloads: empty batches, single-sample batches, zero-length scans,
and scans at typical real LiDAR sizes (e.g. Hokuyo/RPLIDAR ~1080-2000
points).
"""

import sys
import os
import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from flatbuffer_codec import (
    build_imu_batch, read_imu_batch, iter_imu_samples,
    build_encoder_batch, read_encoder_batch, iter_encoder_samples,
    build_laser_scan, read_laser_scan,
)


class TestImuBatch:
    def test_roundtrip_values(self):
        samples = [
            {"timestamp_ns": 1000 + i, "accel": (0.1 * i, 0.2 * i, 9.81),
             "gyro": (0.01 * i, -0.01 * i, 0.0)}
            for i in range(20)
        ]
        buf = build_imu_batch(samples)
        batch = read_imu_batch(buf)
        assert batch.SamplesLength() == 20
        for i, (ts, accel, gyro) in enumerate(iter_imu_samples(batch)):
            assert ts == 1000 + i
            assert accel[0] == pytest.approx(0.1 * i, abs=1e-5)
            assert accel[2] == pytest.approx(9.81, abs=1e-4)
            assert gyro[0] == pytest.approx(0.01 * i, abs=1e-5)

    def test_empty_batch(self):
        buf = build_imu_batch([])
        batch = read_imu_batch(buf)
        assert batch.SamplesLength() == 0
        assert list(iter_imu_samples(batch)) == []

    def test_single_sample(self):
        buf = build_imu_batch([{"timestamp_ns": 42, "accel": (1, 2, 3), "gyro": (4, 5, 6)}])
        batch = read_imu_batch(buf)
        assert batch.SamplesLength() == 1
        ts, accel, gyro = next(iter_imu_samples(batch))
        assert ts == 42 and accel == (1.0, 2.0, 3.0) and gyro == (4.0, 5.0, 6.0)

    def test_high_frequency_batch_size(self):
        # Simulate a typical publish cadence: IMU sampled at 1kHz,
        # batched every 20ms -> 20 samples per message.
        n = 20
        samples = [{"timestamp_ns": i * 1_000_000, "accel": (0, 0, 9.81),
                    "gyro": (0, 0, 0)} for i in range(n)]
        buf = build_imu_batch(samples)
        # sanity: bytes-per-sample should be close to the fixed struct
        # size (32B) plus small table/vector overhead, confirming we
        # aren't paying a large per-message tax at this rate.
        assert len(buf) < 32 * n + 128


class TestEncoderBatch:
    def test_roundtrip_values(self):
        samples = [{"timestamp_ns": i, "left_ticks": 1000 + i, "right_ticks": 1000 - i,
                    "velocity_mps": 0.02 * i} for i in range(15)]
        buf = build_encoder_batch(samples)
        batch = read_encoder_batch(buf)
        result = list(iter_encoder_samples(batch))
        assert len(result) == 15
        for i, (ts, lt, rt, v) in enumerate(result):
            assert ts == i and lt == 1000 + i and rt == 1000 - i
            assert v == pytest.approx(0.02 * i, abs=1e-5)

    def test_negative_ticks_supported(self):
        # e.g. wheel spinning in reverse
        buf = build_encoder_batch([{"timestamp_ns": 0, "left_ticks": -500,
                                     "right_ticks": -10, "velocity_mps": -0.3}])
        batch = read_encoder_batch(buf)
        s = batch.Samples(0)
        assert s.LeftTicks() == -500
        assert s.RightTicks() == -10


class TestLaserScan:
    def test_roundtrip_typical_lidar_size(self):
        n = 1080  # typical Hokuyo-class 2D LiDAR scan width
        ranges = np.random.uniform(0.05, 25.0, size=n).astype(np.float32)
        buf = build_laser_scan(
            timestamp_ns=123_456_789, angle_min=-3.14159, angle_max=3.14159,
            angle_increment=(2 * 3.14159) / n, range_min=0.05, range_max=30.0,
            ranges=ranges,
        )
        scan = read_laser_scan(buf)
        assert scan.TimestampNs() == 123_456_789
        assert scan.RangesLength() == n
        got = scan.RangesAsNumpy()
        np.testing.assert_allclose(got, ranges, rtol=1e-6)

    def test_ranges_as_numpy_is_zero_copy_view(self):
        ranges = np.arange(500, dtype=np.float32)
        buf = build_laser_scan(0, 0, 1, 0.01, 0.1, 10.0, ranges)
        scan = read_laser_scan(buf)
        arr = scan.RangesAsNumpy()
        # A zero-copy numpy view reports a non-None .base (it's a view
        # into someone else's buffer) rather than owning its own memory.
        assert arr.base is not None
        assert arr.flags["OWNDATA"] is False

    def test_large_scan_with_intensities(self):
        n = 2000  # denser LiDAR (e.g. RoboSense/Velodyne single-ring)
        ranges = np.random.uniform(0.1, 50.0, size=n).astype(np.float32)
        intensities = np.random.uniform(0, 255, size=n).astype(np.float32)
        buf = build_laser_scan(0, -np.pi, np.pi, 2 * np.pi / n, 0.1, 60.0,
                                ranges, intensities=intensities)
        scan = read_laser_scan(buf)
        assert scan.RangesLength() == n
        assert scan.IntensitiesLength() == n
        np.testing.assert_allclose(scan.IntensitiesAsNumpy(), intensities, rtol=1e-6)

    def test_scan_without_intensities_reports_none(self):
        ranges = np.ones(100, dtype=np.float32)
        buf = build_laser_scan(0, 0, 1, 0.01, 0.1, 10.0, ranges)
        scan = read_laser_scan(buf)
        assert scan.IntensitiesIsNone() is True

    def test_zero_length_scan(self):
        buf = build_laser_scan(0, 0, 0, 0, 0, 0, ranges=np.array([], dtype=np.float32))
        scan = read_laser_scan(buf)
        assert scan.RangesLength() == 0

    def test_ranges_accepts_plain_python_list(self):
        buf = build_laser_scan(0, 0, 1, 0.1, 0.1, 10, ranges=[1.0, 2.5, 3.75])
        scan = read_laser_scan(buf)
        np.testing.assert_allclose(scan.RangesAsNumpy(), [1.0, 2.5, 3.75])


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
