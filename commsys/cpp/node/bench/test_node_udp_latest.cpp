#include <numeric>
#include "include/node.hpp"
#include <cstdio>
#include <unistd.h>
#include <sys/wait.h>
#include <vector>
#include <cstring>
#include <algorithm>

using namespace commsys;

int main() {
    shm_unlink(REGISTRY_NAME);

    // --- Test 1: UDP basic ---
    {
        pid_t pid = fork();
        if (pid == 0) {
            Node sub("cpp_sub_udp", "127.0.0.1", 0, "udp");
            sub.start();
            std::vector<std::string> received;
            sub.subscribe("ping", [&](const uint8_t* p, uint32_t n) { received.emplace_back((const char*)p, n); });
            auto t_end = std::chrono::steady_clock::now() + std::chrono::seconds(3);
            while (std::chrono::steady_clock::now() < t_end) sub.spin_once(5);
            printf("[udp] received %zu/5\n", received.size());
            fflush(stdout);
            sub.stop();
            _exit(received.size() == 5 ? 0 : 1);
        }
        Node pub("cpp_pub_udp", "127.0.0.1", 0, "udp");
        pub.start();
        pub.advertise("ping");
        auto t_settle = std::chrono::steady_clock::now() + std::chrono::milliseconds(800);
        while (std::chrono::steady_clock::now() < t_settle) pub.spin_once(5);
        for (int i = 0; i < 5; i++) {
            std::string msg = "udp-" + std::to_string(i);
            pub.publish("ping", (const uint8_t*)msg.data(), (uint32_t)msg.size());
            auto t = std::chrono::steady_clock::now() + std::chrono::milliseconds(50);
            while (std::chrono::steady_clock::now() < t) pub.spin_once(5);
        }
        auto t_final = std::chrono::steady_clock::now() + std::chrono::milliseconds(500);
        while (std::chrono::steady_clock::now() < t_final) pub.spin_once(5);
        pub.stop();
        int status; waitpid(pid, &status, 0);
        if (WEXITSTATUS(status) != 0) { printf("UDP TEST FAILED\n"); return 1; }
    }

    // --- Test 2: keep_latest under unpaced firehose ---
    {
        pid_t pid = fork();
        if (pid == 0) {
            Node sub("cpp_sub_kl", "127.0.0.1", 0, "shm");
            sub.start();
            sub.subscribe("imu", [](const uint8_t*, uint32_t) {}, /*keep_latest=*/true);
            auto t_end = std::chrono::steady_clock::now() + std::chrono::seconds(4);
            while (std::chrono::steady_clock::now() < t_end) sub.spin_once(1);
            auto& st = sub.stats("imu");
            printf("[keep_latest] dispatched=%llu\n", (unsigned long long)st.count);
            if (!st.latencies_ms.empty()) {
                auto v = st.latencies_ms;
                std::sort(v.begin(), v.end());
                size_t n = v.size();
                printf("[keep_latest] mean=%.4fms p50=%.4fms p99=%.4fms max=%.4fms\n",
                       std::accumulate(v.begin(), v.end(), 0.0) / n, v[n/2], v[(size_t)(n*0.99)], v.back());
            }
            fflush(stdout);
            sub.stop();
            _exit(0);
        }
        Node pub("cpp_pub_kl", "127.0.0.1", 0, "shm");
        pub.start();
        pub.advertise("imu");
        auto t_settle = std::chrono::steady_clock::now() + std::chrono::milliseconds(800);
        while (std::chrono::steady_clock::now() < t_settle) pub.spin_once(5);

        std::vector<uint8_t> payload(1 << 16, 0);
        auto t_end = std::chrono::steady_clock::now() + std::chrono::seconds(2);
        uint64_t sent = 0;
        while (std::chrono::steady_clock::now() < t_end) {
            pub.publish("imu", payload.data(), (uint32_t)payload.size());
            sent++;
            if ((sent & 0xFFF) == 0) pub.spin_once(0);  // let discovery/heartbeat keep up
        }
        printf("[keep_latest] sent=%llu (unpaced firehose)\n", (unsigned long long)sent);
        fflush(stdout);
        auto t_final = std::chrono::steady_clock::now() + std::chrono::milliseconds(500);
        while (std::chrono::steady_clock::now() < t_final) pub.spin_once(5);
        pub.stop();
        int status; waitpid(pid, &status, 0);
    }

    shm_unlink(REGISTRY_NAME);
    return 0;
}
