// bench_cpu_affinity.cpp
//
// Directly tests whether pinning the publisher and subscriber to
// dedicated CPU cores (sched_setaffinity) reduces the tail latency
// caused by OS scheduling contention -- as opposed to true isolcpus-
// style kernel isolation, which needs a boot parameter and isn't
// something a CI runner or this reference implementation can set up.
// This is the achievable-without-a-reboot version: it doesn't remove
// the target cores from the general scheduler's pool (other system
// processes could still land there), but it does guarantee the
// publisher and subscriber never compete with *each other* for the
// same core, which is the specific contention this project has
// actually measured.
//
// Runs the identical firehose scenario twice: once with no affinity
// set (OS default scheduling) and once with publisher pinned to CPU 0
// and subscriber pinned to CPU 1, so the two are directly comparable
// in one process rather than relying on separate runs.
#include "include/node.hpp"
#include <cstdio>
#include <cstring>
#include <unistd.h>
#include <sys/wait.h>
#include <sched.h>
#include <vector>
#include <algorithm>
#include <numeric>

using namespace commsys;

bool set_affinity(int cpu) {
    cpu_set_t set;
    CPU_ZERO(&set);
    CPU_SET(cpu, &set);
    return sched_setaffinity(0, sizeof(set), &set) == 0;
}

struct Result {
    uint64_t sent = 0, dispatched = 0, drops = 0;
    double mean = 0, p50 = 0, p99 = 0, max_lat = 0;
};

Result run_once(bool pin, int pub_cpu, int sub_cpu) {
    shm_unlink(REGISTRY_NAME);
    int pipefd[2];
    pipe(pipefd);

    pid_t pid = fork();
    if (pid == 0) {
        close(pipefd[0]);
        if (pin) {
            bool ok = set_affinity(sub_cpu);
            if (!ok) fprintf(stderr, "warning: failed to pin subscriber to cpu %d\n", sub_cpu);
        }
        Node sub("aff_sub", "127.0.0.1", 0, "shm");
        sub.start();
        sub.subscribe("scan", [](const uint8_t*, uint32_t) {});
        auto t_end = std::chrono::steady_clock::now() + std::chrono::seconds(4);
        while (std::chrono::steady_clock::now() < t_end) sub.spin_once();
        auto& st = sub.stats("scan");
        Result r;
        r.dispatched = st.count;
        r.drops = st.drops;
        if (!st.latencies_ms.empty()) {
            auto v = st.latencies_ms;
            std::sort(v.begin(), v.end());
            size_t n = v.size();
            r.mean = std::accumulate(v.begin(), v.end(), 0.0) / n;
            r.p50 = v[n / 2];
            r.p99 = v[(size_t)(n * 0.99)];
            r.max_lat = v.back();
        }
        write(pipefd[1], &r, sizeof(r));
        close(pipefd[1]);
        sub.stop();
        _exit(0);
    }
    close(pipefd[1]);
    if (pin) {
        bool ok = set_affinity(pub_cpu);
        if (!ok) fprintf(stderr, "warning: failed to pin publisher to cpu %d\n", pub_cpu);
    }
    Node pub("aff_pub", "127.0.0.1", 0, "shm");
    pub.start();
    pub.advertise("scan");
    auto t_settle = std::chrono::steady_clock::now() + std::chrono::milliseconds(800);
    while (std::chrono::steady_clock::now() < t_settle) pub.spin_once();

    std::vector<uint8_t> payload(1 << 16, 0);
    auto t_end = std::chrono::steady_clock::now() + std::chrono::seconds(2);
    uint64_t sent = 0;
    while (std::chrono::steady_clock::now() < t_end) {
        pub.publish("scan", payload.data(), (uint32_t)payload.size());
        sent++;
    }
    auto t_final = std::chrono::steady_clock::now() + std::chrono::milliseconds(500);
    while (std::chrono::steady_clock::now() < t_final) pub.spin_once();
    pub.stop();

    Result result{};
    read(pipefd[0], &result, sizeof(result));
    close(pipefd[0]);
    result.sent = sent;
    int status;
    waitpid(pid, &status, 0);
    shm_unlink(REGISTRY_NAME);
    return result;
}

void print_result(const char* label, const Result& r) {
    printf("%-40s sent=%8llu dispatched=%8llu drops=%6llu mean=%8.4fms p50=%8.4fms p99=%8.4fms max=%9.4fms\n",
           label, (unsigned long long)r.sent, (unsigned long long)r.dispatched, (unsigned long long)r.drops,
           r.mean, r.p50, r.p99, r.max_lat);
}

int main() {
    long ncpu = sysconf(_SC_NPROCESSORS_ONLN);
    printf("nproc=%ld\n\n", ncpu);

    if (ncpu < 2) {
        printf("Only 1 CPU available -- core isolation is structurally meaningless here\n");
        printf("(nothing to isolate the publisher and subscriber FROM; they must share\n");
        printf("the single core regardless of any affinity setting). Running the\n");
        printf("unpinned case only, for the record:\n\n");
        auto r = run_once(false, 0, 0);
        print_result("unpinned (only option on 1 core)", r);
        return 0;
    }

    printf("=== Unpinned (OS default scheduling) ===\n");
    for (int i = 0; i < 3; i++) {
        auto r = run_once(false, 0, 0);
        print_result("unpinned", r);
    }

    printf("\n=== Pinned: publisher->CPU0, subscriber->CPU1 ===\n");
    for (int i = 0; i < 3; i++) {
        auto r = run_once(true, 0, 1);
        print_result("pinned", r);
    }

    return 0;
}
