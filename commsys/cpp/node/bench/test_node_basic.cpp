#include "include/node.hpp"
#include <cstdio>
#include <unistd.h>
#include <sys/wait.h>
#include <vector>
#include <cstring>

using namespace commsys;

int main() {
    shm_unlink(REGISTRY_NAME);
    pid_t pid = fork();
    if (pid == 0) {
        // subscriber
        Node sub("cpp_sub_basic", "127.0.0.1", 0, "shm");
        sub.start();
        std::vector<std::string> received;
        sub.subscribe("greeting", [&](const uint8_t* p, uint32_t n) {
            received.emplace_back((const char*)p, n);
        });
        auto t_end = std::chrono::steady_clock::now() + std::chrono::seconds(3);
        while (std::chrono::steady_clock::now() < t_end) sub.spin_once(5);
        printf("[sub] received %zu messages:\n", received.size());
        for (auto& s : received) printf("  %s\n", s.c_str());
        fflush(stdout);
        sub.stop();
        _exit(received.size() == 5 ? 0 : 1);
    }
    // publisher
    Node pub("cpp_pub_basic", "127.0.0.1", 0, "shm");
    pub.start();
    pub.advertise("greeting");
    auto t_settle = std::chrono::steady_clock::now() + std::chrono::milliseconds(800);
    while (std::chrono::steady_clock::now() < t_settle) pub.spin_once(5);
    for (int i = 0; i < 5; i++) {
        std::string msg = "hello-" + std::to_string(i);
        pub.publish("greeting", (const uint8_t*)msg.data(), (uint32_t)msg.size());
        auto t = std::chrono::steady_clock::now() + std::chrono::milliseconds(50);
        while (std::chrono::steady_clock::now() < t) pub.spin_once(5);
    }
    auto t_final = std::chrono::steady_clock::now() + std::chrono::milliseconds(500);
    while (std::chrono::steady_clock::now() < t_final) pub.spin_once(5);
    pub.stop();

    int status;
    waitpid(pid, &status, 0);
    shm_unlink(REGISTRY_NAME);
    printf("subscriber exit status: %d\n", WEXITSTATUS(status));
    return WEXITSTATUS(status);
}
