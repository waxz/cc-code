#include "include/node.hpp"
#include <cstdio>
#include <cstring>
#include <unistd.h>
#include <sys/wait.h>
#include <vector>

using namespace commsys;

struct ImuSample {
    uint64_t timestamp_ns;
    float ax, ay, az;
    float gx, gy, gz;
};

int main() {
    shm_unlink(REGISTRY_NAME);
    pid_t pid = fork();
    if (pid == 0) {
        // subscriber
        Node sub("typed_sub", {.force_transport = "shm"});
        sub.start();

        std::vector<ImuSample> received_imu;
        sub.subscribe<ImuSample>("imu", [&](const ImuSample& msg) {
            received_imu.push_back(msg);
        });

        std::vector<std::vector<uint8_t>> received_raw;
        sub.subscribe<RawBytes>("blob", [&](const RawBytes& raw) {
            received_raw.emplace_back(raw.data, raw.data + raw.size);
        });

        sub.spin_for(std::chrono::seconds(3));

        bool ok = true;
        printf("[sub] received %zu ImuSample messages\n", received_imu.size());
        for (size_t i = 0; i < received_imu.size(); i++) {
            auto& m = received_imu[i];
            if (m.timestamp_ns != i || m.ax != (float)i * 0.1f) {
                printf("  MISMATCH at %zu: ts=%llu ax=%.3f\n", i,
                       (unsigned long long)m.timestamp_ns, m.ax);
                ok = false;
            }
        }
        printf("[sub] received %zu RawBytes blobs\n", received_raw.size());
        for (size_t i = 0; i < received_raw.size(); i++) {
            std::string expected = "blob-" + std::to_string(i);
            std::string got(received_raw[i].begin(), received_raw[i].end());
            if (got != expected) {
                printf("  MISMATCH at %zu: got=%s expected=%s\n", i, got.c_str(), expected.c_str());
                ok = false;
            }
        }
        if (received_imu.size() != 5 || received_raw.size() != 3) ok = false;
        fflush(stdout);
        sub.stop();
        _exit(ok ? 0 : 1);
    }

    // publisher
    Node pub("typed_pub", {.force_transport = "shm"});
    pub.start();
    pub.advertise("imu");
    pub.advertise("blob");
    pub.spin_for(std::chrono::milliseconds(800));

    for (int i = 0; i < 5; i++) {
        ImuSample sample{(uint64_t)i, (float)i * 0.1f, 0.0f, 9.81f, 0.0f, 0.0f, 0.0f};
        pub.publish("imu", sample);  // typed publish, deduces ImuSample
        pub.spin_for(std::chrono::milliseconds(20));
    }

    for (int i = 0; i < 3; i++) {
        std::string blob = "blob-" + std::to_string(i);
        pub.publish("blob", RawBytes((const uint8_t*)blob.data(), (uint32_t)blob.size()));
        pub.spin_for(std::chrono::milliseconds(20));
    }

    pub.spin_for(std::chrono::milliseconds(500));
    pub.stop();

    int status;
    waitpid(pid, &status, 0);
    shm_unlink(REGISTRY_NAME);
    int rc = WEXITSTATUS(status);
    printf("typed API end-to-end test: %s\n", rc == 0 ? "PASS" : "FAIL");
    return rc;
}
