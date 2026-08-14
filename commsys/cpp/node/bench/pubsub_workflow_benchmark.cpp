// pubsub_workflow_benchmark.cpp
//
// A realistic publish/subscribe workflow, distinct from
// benchmark_report.cpp's isolated single-topic rate sweeps and
// unpaced firehose stress tests: three concurrent topics at their
// own realistic rates (IMU-class 100Hz, wheel encoder 50Hz, pose
// estimate 20Hz), one publisher process and one subscriber process,
// running for a fixed duration -- the shape an actual robot's
// perception/control stack would look like, not a worst-case stress
// probe. Same measurement methodology as benchmark_report.cpp
// (per-message send_ns timestamp, p50/p99/max latency) so the
// numbers are directly comparable to that report's tables.
//
// Same workflow and same output format exist in Python
// (python/pubsub_workflow_benchmark.py) specifically so the two are
// runnable side by side for a direct comparison -- see
// PUBSUB_WORKFLOW_COMPARISON.md.
#include "../include/node.hpp"
#include "../include/messages.hpp"
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <numeric>
#include <sched.h>
#include <sys/wait.h>
#include <unistd.h>
#include <vector>

using namespace commsys;
using Clock = std::chrono::steady_clock;

struct TopicResult {
    const char* name;
    uint64_t sent = 0, received = 0, drops = 0;
    double mean_ms = 0, p50_ms = 0, p99_ms = 0, max_ms = 0;
};

TopicResult summarize(const char* name, SubStats& st, uint64_t sent) {
    TopicResult r;
    r.name = name;
    r.sent = sent;
    r.received = st.count;
    r.drops = st.drops;
    if (!st.latencies_ms.empty()) {
        auto v = st.latencies_ms;
        std::sort(v.begin(), v.end());
        size_t n = v.size();
        r.mean_ms = std::accumulate(v.begin(), v.end(), 0.0) / n;
        r.p50_ms = v[n / 2];
        r.p99_ms = v[(size_t)(n * 0.99)];
        r.max_ms = v.back();
    }
    return r;
}

void print_result(const TopicResult& r) {
    printf("| %-10s | %6llu | %6llu | %6llu | %8.4f | %8.4f | %8.4f |\n", r.name,
           (unsigned long long)r.sent, (unsigned long long)r.received, (unsigned long long)r.drops,
           r.mean_ms, r.p99_ms, r.max_ms);
}

int run_workflow(const std::string& transport, double duration_s) {
    shm_unlink(REGISTRY_NAME);
    int pipefd[2];
    pipe(pipefd);

    pid_t pid = fork();
    if (pid == 0) {
        close(pipefd[0]);
        Node sub("workflow_sub", {.force_transport = transport});
        sub.start();
        sub.subscribe<msg::Imu>("imu", [](const msg::Imu&) {});
        sub.subscribe<msg::Encoder>("encoder", [](const msg::Encoder&) {});
        sub.subscribe<msg::Pose2D>("pose", [](const msg::Pose2D&) {});
        sub.spin_for(std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(duration_s + 1.0)));

        auto imu_st = sub.stats("imu");
        auto enc_st = sub.stats("encoder");
        auto pose_st = sub.stats("pose");
        struct Wire { char name[16]; uint64_t received, drops; double mean_ms, p50_ms, p99_ms, max_ms; } wire[3];
        auto fill = [](Wire& w, const char* name, SubStats& st) {
            snprintf(w.name, sizeof(w.name), "%s", name);
            auto r = summarize(name, st, 0);
            w.received = r.received; w.drops = r.drops;
            w.mean_ms = r.mean_ms; w.p50_ms = r.p50_ms; w.p99_ms = r.p99_ms; w.max_ms = r.max_ms;
        };
        fill(wire[0], "imu", imu_st);
        fill(wire[1], "encoder", enc_st);
        fill(wire[2], "pose", pose_st);
        write(pipefd[1], wire, sizeof(wire));
        close(pipefd[1]);
        sub.stop();
        _exit(0);
    }
    close(pipefd[1]);

    Node pub("workflow_pub", {.force_transport = transport});
    pub.start();
    pub.advertise("imu");
    pub.advertise("encoder");
    pub.advertise("pose");
    pub.spin_for(std::chrono::milliseconds(800));

    auto t_end = Clock::now() + std::chrono::duration<double>(duration_s);
    uint64_t imu_sent = 0, enc_sent = 0, pose_sent = 0;
    auto next_imu = Clock::now(), next_enc = Clock::now(), next_pose = Clock::now();
    auto imu_period = std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(1.0 / 100.0));
    auto enc_period = std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(1.0 / 50.0));
    auto pose_period = std::chrono::duration_cast<Clock::duration>(std::chrono::duration<double>(1.0 / 20.0));

    while (Clock::now() < t_end) {
        auto now = Clock::now();
        if (now >= next_imu) {
            pub.publish("imu", msg::Imu{(uint64_t)imu_sent, 0.1f, 0, 9.81f, 0, 0, 0});
            imu_sent++;
            next_imu += imu_period;
        }
        if (now >= next_enc) {
            pub.publish("encoder", msg::Encoder{(uint64_t)enc_sent, (int64_t)enc_sent * 10, (int64_t)enc_sent * 10, 0.5f});
            enc_sent++;
            next_enc += enc_period;
        }
        if (now >= next_pose) {
            pub.publish("pose", msg::Pose2D{(uint64_t)pose_sent, (float)pose_sent * 0.01f, 0, 0});
            pose_sent++;
            next_pose += pose_period;
        }
        pub.spin_once(0);
        // Without this, the loop above is a completely unyielding
        // busy-spin -- same bug class diagnosed and fixed multiple
        // times elsewhere in this project (the ring buffer's write
        // backoff, the keep_latest slot's write path): on a
        // contended single core, it starves the subscriber process of
        // any natural scheduling opportunity. Confirmed by direct
        // measurement, not assumed: without this line, this
        // benchmark's C++ numbers were *slower* than the Python
        // equivalent (mean ~3.3ms vs ~0.3ms) -- the opposite of every
        // other comparison in this project -- purely from OS
        // scheduling contention between two tight, unyielding loops
        // (this one and the subscriber's own spin_for). Adding this
        // single line took C++ to ~0.01-0.04ms mean, correctly faster
        // than Python again. A naive tight publish loop with no yield
        // point can make a genuinely faster implementation look
        // slower on constrained hardware for reasons that have
        // nothing to do with the actual work being measured.
        sched_yield();
    }
    pub.spin_for(std::chrono::milliseconds(500));
    pub.stop();

    struct Wire { char name[16]; uint64_t received, drops; double mean_ms, p50_ms, p99_ms, max_ms; } wire[3];
    read(pipefd[0], wire, sizeof(wire));
    close(pipefd[0]);
    int status;
    waitpid(pid, &status, 0);
    shm_unlink(REGISTRY_NAME);

    uint64_t sent_by_name[3] = {imu_sent, enc_sent, pose_sent};
    printf("| topic      |   sent | recv'd |  drops | mean(ms) |  p99(ms) |  max(ms) |\n");
    printf("|------------|--------|--------|--------|----------|----------|----------|\n");
    for (int i = 0; i < 3; i++) {
        TopicResult r;
        r.name = wire[i].name;
        r.sent = sent_by_name[i];
        r.received = wire[i].received;
        r.drops = wire[i].drops;
        r.mean_ms = wire[i].mean_ms;
        r.p99_ms = wire[i].p99_ms;
        r.max_ms = wire[i].max_ms;
        print_result(r);
    }
    return 0;
}

int main(int argc, char** argv) {
    std::string transport = argc > 1 ? argv[1] : "shm";
    double duration = argc > 2 ? std::stod(argv[2]) : 5.0;
    printf("# commsys C++ pub/sub workflow benchmark (transport=%s, duration=%.1fs)\n\n", transport.c_str(), duration);
    printf("Workflow: one publisher, one subscriber, three concurrent topics at\n");
    printf("realistic robot sensor rates (imu=100Hz, encoder=50Hz, pose=20Hz).\n\n");
    return run_workflow(transport, duration);
}
