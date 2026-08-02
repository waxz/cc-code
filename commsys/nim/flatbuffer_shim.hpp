// flatbuffer_shim.hpp
//
// Thin C++ wrapper around the generated FlatBuffers API, exposed as
// plain free functions so Nim can bind to them directly via
// {.importcpp.} -- demonstrating real interop with the *actual*
// FlatBuffers C++ library (the same one bench_flatbuffers.cpp uses),
// not a Nim reimplementation of FlatBuffers' wire format.
#pragma once
#include "generated/robot_msgs_generated.h"
#include <cstdint>
#include <cstring>
#include <vector>

using namespace RobotMsgs;

// Reusable builder + backing storage so repeated calls don't pay for
// reallocating the FlatBufferBuilder's internal buffer every time --
// mirrors how a real hot-path publisher would reuse one builder.
struct ImuBatchHandle {
    flatbuffers::FlatBufferBuilder fbb;
    std::vector<uint8_t> last;
    ImuBatchHandle() : fbb(1024) {}
};

inline ImuBatchHandle* imu_builder_new() { return new ImuBatchHandle(); }
inline void imu_builder_free(ImuBatchHandle* b) { delete b; }

// samples: interleaved [timestamp_ns(as double for simplicity), ax,ay,az,gx,gy,gz] * n
inline size_t imu_build(ImuBatchHandle* b, const double* ts, const float* accel_gyro, int n) {
    b->fbb.Clear();
    std::vector<ImuSample> samples;
    samples.reserve(n);
    for (int i = 0; i < n; i++) {
        const float* p = accel_gyro + i * 6;
        samples.emplace_back(ImuSample((uint64_t)ts[i], Vec3(p[0], p[1], p[2]), Vec3(p[3], p[4], p[5])));
    }
    auto vec = b->fbb.CreateVectorOfStructs(samples);
    auto batch = CreateImuBatch(b->fbb, vec);
    b->fbb.Finish(batch);
    b->last.assign(b->fbb.GetBufferPointer(), b->fbb.GetBufferPointer() + b->fbb.GetSize());
    return b->last.size();
}

inline const uint8_t* imu_builder_data(ImuBatchHandle* b) { return b->last.data(); }

// Reads a previously built buffer and sums accel.z across all samples
// -- exercises the zero-copy read path (no reimplementation, calls
// straight into the generated accessor methods).
inline float imu_read_sum(const uint8_t* buf) {
    auto* batch = flatbuffers::GetRoot<ImuBatch>(buf);
    float total = 0;
    for (auto s : *batch->samples()) total += s->accel().z();
    return total;
}

// --- LaserScan ---
struct LaserScanBuilderHandle {
    flatbuffers::FlatBufferBuilder fbb;
    std::vector<uint8_t> last;
    LaserScanBuilderHandle(size_t reserve) : fbb((unsigned int)reserve) {}
};

inline LaserScanBuilderHandle* laser_builder_new(int n_points) {
    return new LaserScanBuilderHandle(n_points * 4 + 256);
}
inline void laser_builder_free(LaserScanBuilderHandle* b) { delete b; }

inline size_t laser_build(LaserScanBuilderHandle* b, uint64_t ts, float angle_min,
                           float angle_max, float angle_inc, float range_min,
                           float range_max, const float* ranges, int n) {
    b->fbb.Clear();
    auto ranges_vec = b->fbb.CreateVector(ranges, n);
    RobotMsgs::LaserScanBuilder lb(b->fbb);
    lb.add_timestamp_ns(ts);
    lb.add_angle_min(angle_min);
    lb.add_angle_max(angle_max);
    lb.add_angle_increment(angle_inc);
    lb.add_range_min(range_min);
    lb.add_range_max(range_max);
    lb.add_ranges(ranges_vec);
    auto scan = lb.Finish();
    b->fbb.Finish(scan);
    b->last.assign(b->fbb.GetBufferPointer(), b->fbb.GetBufferPointer() + b->fbb.GetSize());
    return b->last.size();
}

inline const uint8_t* laser_builder_data(LaserScanBuilderHandle* b) { return b->last.data(); }

inline float laser_read_sum(const uint8_t* buf) {
    auto* scan = flatbuffers::GetRoot<LaserScan>(buf);
    float total = 0;
    for (auto v : *scan->ranges()) total += v;
    return total;
}
