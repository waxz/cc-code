// bench_flatbuffers.cpp
// Mirrors benchmark_serialization.py's IMU batch and LaserScan cases,
// using the same schema (robot_msgs.fbs) compiled to C++.
#include "generated/robot_msgs_generated.h"
#include <cstdio>
#include <vector>
#include <random>
#include <chrono>
#include <algorithm>
#include <numeric>

using Clock = std::chrono::high_resolution_clock;
using namespace RobotMsgs;

struct Stats { double mean_ns, p50_ns, p99_ns; };

template <typename Fn>
Stats timed(Fn fn, int iters, int warmup = 50) {
    for (int i = 0; i < warmup; i++) fn();
    std::vector<double> samples;
    samples.reserve(iters);
    for (int i = 0; i < iters; i++) {
        auto t0 = Clock::now();
        fn();
        auto t1 = Clock::now();
        samples.push_back(std::chrono::duration<double, std::nano>(t1 - t0).count());
    }
    std::sort(samples.begin(), samples.end());
    double mean = std::accumulate(samples.begin(), samples.end(), 0.0) / samples.size();
    return {mean, samples[samples.size() / 2], samples[(size_t)(samples.size() * 0.99)]};
}

void print_row(const char* name, Stats s, size_t bytes) {
    printf("  %-32s mean=%8.2fus  p50=%8.2fus  p99=%8.2fus  size=%7zuB\n",
           name, s.mean_ns / 1000.0, s.p50_ns / 1000.0, s.p99_ns / 1000.0, bytes);
}

void bench_imu(int n, int iters) {
    printf("\n=== C++ FlatBuffers IMU batch (n=%d samples/msg) ===\n", n);

    flatbuffers::FlatBufferBuilder fbb(1024);
    auto build = [&]() {
        fbb.Clear();
        std::vector<ImuSample> samples;
        samples.reserve(n);
        for (int i = 0; i < n; i++)
            samples.emplace_back(ImuSample(i, Vec3(0.1f, 0.2f, 9.81f), Vec3(0.01f, 0.02f, 0.03f)));
        auto vec = fbb.CreateVectorOfStructs(samples);
        auto batch = CreateImuBatch(fbb, vec);
        fbb.Finish(batch);
    };
    auto s1 = timed(build, iters);

    build();  // leave a valid buffer in fbb for the read benchmark
    std::vector<uint8_t> saved(fbb.GetBufferPointer(), fbb.GetBufferPointer() + fbb.GetSize());
    print_row("build", s1, saved.size());

    auto read_and_sum = [&]() {
        auto* batch = flatbuffers::GetRoot<ImuBatch>(saved.data());
        volatile float total = 0;
        for (auto s : *batch->samples()) total += s->accel().z();
        return total;
    };
    auto s2 = timed(read_and_sum, iters);
    print_row("read+sum (zero-copy)", s2, saved.size());
}

void bench_laser_scan(int n_points, int iters) {
    printf("\n=== C++ FlatBuffers LaserScan (n=%d points) ===\n", n_points);
    std::mt19937 rng(42);
    std::uniform_real_distribution<float> dist(0.05f, 25.0f);
    std::vector<float> ranges(n_points);
    for (auto& r : ranges) r = dist(rng);

    flatbuffers::FlatBufferBuilder fbb(n_points * 4 + 256);
    auto build = [&]() {
        fbb.Clear();
        auto ranges_vec = fbb.CreateVector(ranges);
        LaserScanBuilder lb(fbb);
        lb.add_timestamp_ns(1);
        lb.add_angle_min(-3.14f);
        lb.add_angle_max(3.14f);
        lb.add_angle_increment(0.0058f);
        lb.add_range_min(0.05f);
        lb.add_range_max(30.0f);
        lb.add_ranges(ranges_vec);
        auto scan = lb.Finish();
        fbb.Finish(scan);
    };
    auto s1 = timed(build, iters);
    build();
    std::vector<uint8_t> saved(fbb.GetBufferPointer(), fbb.GetBufferPointer() + fbb.GetSize());
    print_row("build (from std::vector<float>)", s1, saved.size());

    auto read_view = [&]() {
        auto* scan = flatbuffers::GetRoot<LaserScan>(saved.data());
        return scan->ranges();  // zero-copy accessor, no element touched yet
    };
    auto s2 = timed(read_view, iters);
    print_row("read (zero-copy view)", s2, saved.size());

    auto read_and_sum = [&]() {
        auto* scan = flatbuffers::GetRoot<LaserScan>(saved.data());
        volatile float total = 0;
        for (auto v : *scan->ranges()) total += v;
        return total;
    };
    auto s3 = timed(read_and_sum, iters);
    print_row("read+sum (all elements)", s3, saved.size());
}

int main() {
    bench_imu(20, 100000);
    bench_imu(1, 200000);
    bench_laser_scan(1080, 50000);
    bench_laser_scan(2000, 30000);
    return 0;
}
