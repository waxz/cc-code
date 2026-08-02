// benchmark_report.cpp
//
// Mirrors benchmark_report.py's scenario matrix exactly (same rates,
// same payload sizes, same durations) for a direct, apples-to-apples
// comparison against the Python numbers already measured.
#include "../include/node.hpp"
#include <algorithm>
#include <cstdio>
#include <numeric>
#include <sys/wait.h>
#include <unistd.h>
#include <vector>
#include <cmath>
#include <thread>

using namespace commsys;
using Clock = std::chrono::steady_clock;

struct Stats {
    uint64_t count = 0, drops = 0, bytes = 0;
    double mean = 0, p50 = 0, p99 = 0, max_lat = 0;
};

Stats compute_stats(SubStats& st, double duration_s) {
    Stats s;
    s.count = st.count;
    s.drops = st.drops;
    s.bytes = st.bytes_total;
    if (!st.latencies_ms.empty()) {
        auto v = st.latencies_ms;
        std::sort(v.begin(), v.end());
        size_t n = v.size();
        s.mean = std::accumulate(v.begin(), v.end(), 0.0) / n;
        s.p50 = v[n / 2];
        s.p99 = v[(size_t)(n * 0.99)];
        s.max_lat = v.back();
    }
    return s;
}

// Runs one publisher and one subscriber as forked processes, waits
// for the subscriber to report back over a pipe, returns its stats.
Stats run_scenario(const std::string& topic, uint32_t payload_size, double rate_hz /*0=unpaced*/,
                    const std::string& transport, double duration_s, double settle_s = 0.8) {
    shm_unlink(REGISTRY_NAME);
    int pipefd[2];
    pipe(pipefd);

    pid_t sub_pid = fork();
    if (sub_pid == 0) {
        close(pipefd[0]);
        Node sub("bench_sub", "127.0.0.1", 0, transport);
        sub.start();
        sub.subscribe(topic, [](const uint8_t*, uint32_t) {});
        auto t_end = Clock::now() + std::chrono::duration<double>(settle_s + duration_s + 0.5);
        while (Clock::now() < t_end) sub.spin_once();
        Stats s = compute_stats(sub.stats(topic), duration_s);
        write(pipefd[1], &s, sizeof(s));
        close(pipefd[1]);
        sub.stop();
        _exit(0);
    }
    close(pipefd[1]);

    Node pub("bench_pub", "127.0.0.1", 0, transport);
    pub.start();
    pub.advertise(topic);
    auto t_settle = Clock::now() + std::chrono::duration<double>(settle_s);
    while (Clock::now() < t_settle) pub.spin_once();

    std::vector<uint8_t> payload(payload_size, 0);
    auto t_end = Clock::now() + std::chrono::duration<double>(duration_s);
    if (rate_hz > 0) {
        auto period = std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(1.0 / rate_hz));
        while (Clock::now() < t_end) {
            auto next = Clock::now() + period;
            pub.publish(topic, payload.data(), payload_size);
            pub.spin_once();  // one quick non-blocking check, then actually sleep
            auto remaining = next - Clock::now();
            if (remaining > std::chrono::milliseconds(0)) std::this_thread::sleep_for(remaining);
        }
    } else {
        while (Clock::now() < t_end) pub.publish(topic, payload.data(), payload_size);
    }
    auto t_final = Clock::now() + std::chrono::milliseconds(500);
    while (Clock::now() < t_final) pub.spin_once();
    pub.stop();

    Stats result{};
    read(pipefd[0], &result, sizeof(result));
    close(pipefd[0]);
    int status;
    waitpid(sub_pid, &status, 0);
    shm_unlink(REGISTRY_NAME);
    return result;
}

void print_row(const char* label, const Stats& s, double duration_s) {
    double mbps = (s.bytes / duration_s) / 1e6;
    printf("| %-28s | %8llu | %6llu | %10.4f MB/s | %9.4fms | %9.4fms | %9.4fms |\n",
           label, (unsigned long long)s.count, (unsigned long long)s.drops, mbps, s.mean, s.p99, s.max_lat);
}

int main() {
    printf("# commsys C++ benchmark report\n\n"); fflush(stdout);
    printf("Same scenario matrix as benchmark_report.py, same machine, same 2.5s "
           "steady-state duration after 0.8s discovery settle.\n\n");

    printf("## 1. IMU rate sweep (single publisher -> single subscriber, 32B payload)\n\n");
    printf("| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |\n");
    printf("|------------------------------|---------|--------|--------------|-----------|-----------|-----------|\n");
    for (const char* transport : {"shm", "udp"}) {
        for (double rate : {500.0, 1000.0, 2000.0, 5000.0, 10000.0}) {
            auto s = run_scenario("imu", 32, rate, transport, 2.5);
            char label[64];
            snprintf(label, sizeof(label), "%.0fHz %s", rate, transport);
            print_row(label, s, 2.5);
            fflush(stdout);
        }
    }
    printf("\n");

    printf("## 2. LaserScan rate sweep (2000-point-equivalent payload, ~8KB)\n\n");
    printf("| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |\n");
    printf("|------------------------------|---------|--------|--------------|-----------|-----------|-----------|\n");
    for (const char* transport : {"shm", "udp"}) {
        for (double rate : {10.0, 20.0, 40.0, 60.0}) {
            auto s = run_scenario("scan", 8064, rate, transport, 2.5);
            char label[64];
            snprintf(label, sizeof(label), "%.0fHz %s", rate, transport);
            print_row(label, s, 2.5);
            fflush(stdout);
        }
    }
    printf("\n");

    printf("## 3. Unpaced firehose (worst case, no publisher pacing at all)\n\n");
    printf("| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |\n");
    printf("|------------------------------|---------|--------|--------------|-----------|-----------|-----------|\n");
    {
        auto s = run_scenario("imu64k", 1 << 16, 0, "shm", 2.0);
        print_row("64KB FIFO ring, shm", s, 2.0);
    }
    printf("\n");

    return 0;
}
