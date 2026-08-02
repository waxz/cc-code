#include "include/node.hpp"
#include <cstdio>
#include <unistd.h>
#include <sys/wait.h>
#include <vector>
#include <algorithm>
#include <numeric>
#include <cstring>

using namespace commsys;

int main() {
    shm_unlink(REGISTRY_NAME);
    pid_t pid = fork();
    if (pid == 0) {
        Node sub("cpp_sub_ring", "127.0.0.1", 0, "shm");
        sub.start();
        sub.subscribe("scan", [](const uint8_t*, uint32_t) {});  // default: FIFO ring
        auto t_end = std::chrono::steady_clock::now() + std::chrono::seconds(4);
        while (std::chrono::steady_clock::now() < t_end) sub.spin_once();
        auto& st = sub.stats("scan");
        printf("[fifo ring] dispatched=%llu drops=%llu\n", (unsigned long long)st.count, (unsigned long long)st.drops);
        if (!st.latencies_ms.empty()) {
            auto v = st.latencies_ms;
            std::sort(v.begin(), v.end());
            size_t n = v.size();
            printf("[fifo ring] mean=%.4fms p50=%.4fms p99=%.4fms max=%.4fms\n",
                   std::accumulate(v.begin(), v.end(), 0.0) / n, v[n/2], v[(size_t)(n*0.99)], v.back());
        }
        fflush(stdout);
        sub.stop();
        _exit(0);
    }
    Node pub("cpp_pub_ring", "127.0.0.1", 0, "shm");
    pub.start();
    pub.advertise("scan");
    auto t_settle = std::chrono::steady_clock::now() + std::chrono::milliseconds(800);
    while (std::chrono::steady_clock::now() < t_settle) pub.spin_once();

    std::vector<uint8_t> payload(1 << 16, 0);  // 64KB, matches the earlier Python stress test
    auto t_end = std::chrono::steady_clock::now() + std::chrono::seconds(2);
    uint64_t sent = 0;
    while (std::chrono::steady_clock::now() < t_end) {
        pub.publish("scan", payload.data(), (uint32_t)payload.size());
        sent++;
    }
    printf("[fifo ring] sent=%llu (unpaced firehose)\n", (unsigned long long)sent);
    fflush(stdout);
    auto t_final = std::chrono::steady_clock::now() + std::chrono::milliseconds(500);
    while (std::chrono::steady_clock::now() < t_final) pub.spin_once();
    pub.stop();
    int status; waitpid(pid, &status, 0);
    shm_unlink(REGISTRY_NAME);
    return 0;
}
