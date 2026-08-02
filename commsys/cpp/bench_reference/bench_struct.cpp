// bench_struct.cpp
// Raw fixed-layout IMU sample encode/decode, mirroring the Python
// struct.pack/unpack_from benchmark exactly (same wire layout:
// uint64 timestamp + 6x float32 accel/gyro = 32 bytes/sample).
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <vector>
#include <chrono>
#include <algorithm>
#include <numeric>

#pragma pack(push, 1)
struct ImuSampleRaw {
    uint64_t timestamp_ns;
    float ax, ay, az;
    float gx, gy, gz;
};
#pragma pack(pop)
static_assert(sizeof(ImuSampleRaw) == 32, "unexpected padding");

using Clock = std::chrono::high_resolution_clock;

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

int main() {
    printf("=== C++ raw struct IMU batch (n=20 samples/msg) ===\n");
    const int n = 20;
    std::vector<ImuSampleRaw> samples(n);
    for (int i = 0; i < n; i++)
        samples[i] = {static_cast<uint64_t>(i), 0.1f, 0.2f, 9.81f, 0.01f, 0.02f, 0.03f};

    std::vector<uint8_t> buf(n * sizeof(ImuSampleRaw));

    auto pack = [&]() {
        std::memcpy(buf.data(), samples.data(), samples.size() * sizeof(ImuSampleRaw));
    };
    auto s1 = timed(pack, 200000);
    print_row("pack (memcpy)", s1, buf.size());

    auto unpack_and_sum = [&]() {
        volatile float total = 0;
        auto* p = reinterpret_cast<const ImuSampleRaw*>(buf.data());
        for (int i = 0; i < n; i++) total += p[i].az;
        return total;
    };
    auto s2 = timed(unpack_and_sum, 200000);
    print_row("unpack+sum (in place, no copy)", s2, buf.size());

    printf("\n=== C++ raw struct IMU (n=1 sample/msg) ===\n");
    ImuSampleRaw one = {123, 0.1f, 0.2f, 9.81f, 0.01f, 0.02f, 0.03f};
    uint8_t buf1[sizeof(ImuSampleRaw)];
    auto pack1 = [&]() { std::memcpy(buf1, &one, sizeof(one)); };
    auto s3 = timed(pack1, 300000);
    print_row("pack (memcpy)", s3, sizeof(one));

    auto unpack1 = [&]() {
        auto* p = reinterpret_cast<const ImuSampleRaw*>(buf1);
        volatile float v = p->az;
        return v;
    };
    auto s4 = timed(unpack1, 300000);
    print_row("unpack (in place)", s4, sizeof(one));

    return 0;
}
