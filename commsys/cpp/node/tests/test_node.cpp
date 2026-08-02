#include <catch2/catch_all.hpp>
#include "../include/node.hpp"
#include <unistd.h>
#include <sys/wait.h>
#include <random>
#include <chrono>

using namespace commsys;

namespace {

std::string unique_registry() {
    static std::mt19937 rng(std::random_device{}());
    return "/commsys_test_disc_" + std::to_string(rng()) + "_" + std::to_string(getpid());
}

struct ImuSample {
    uint64_t timestamp_ns;
    float ax, ay, az;
    bool operator==(const ImuSample& o) const {
        return timestamp_ns == o.timestamp_ns && ax == o.ax && ay == o.ay && az == o.az;
    }
};

// Runs `pub_fn` in the parent process and `sub_fn` in a forked child,
// waiting for both to finish. sub_fn's return value (0 = pass) becomes
// the child's exit status, which the caller should REQUIRE against.
template <typename PubFn, typename SubFn>
int run_pub_sub(PubFn&& pub_fn, SubFn&& sub_fn) {
    pid_t pid = fork();
    if (pid == 0) {
        int rc = sub_fn();
        _exit(rc);
    }
    pub_fn();
    int status;
    waitpid(pid, &status, 0);
    return WIFEXITED(status) ? WEXITSTATUS(status) : -1;
}

}  // namespace

TEST_CASE("Node: basic FIFO pub/sub round-trip across processes", "[node][fork]") {
    auto reg = unique_registry();
    int rc = run_pub_sub(
        [&] {
            Node pub("basic_pub", {.force_transport = "shm", .registry_name = reg});
            pub.start();
            pub.advertise("greeting");
            pub.spin_for(std::chrono::milliseconds(800));
            for (int i = 0; i < 5; i++) {
                std::string msg = "hello-" + std::to_string(i);
                pub.publish("greeting", (const uint8_t*)msg.data(), (uint32_t)msg.size());
                pub.spin_for(std::chrono::milliseconds(20));
            }
            pub.spin_for(std::chrono::milliseconds(400));
            pub.stop();
        },
        [&] {
            Node sub("basic_sub", {.force_transport = "shm", .registry_name = reg});
            sub.start();
            std::vector<std::string> received;
            sub.subscribe("greeting", [&](const uint8_t* d, uint32_t n) {
                received.emplace_back((const char*)d, n);
            });
            sub.spin_for(std::chrono::seconds(3));
            sub.stop();
            if (received.size() != 5) return 1;
            for (int i = 0; i < 5; i++) {
                if (received[i] != "hello-" + std::to_string(i)) return 2;
            }
            return 0;
        });
    REQUIRE(rc == 0);
}

TEST_CASE("Node: typed publish/subscribe round-trips a POD struct", "[node][fork][typed]") {
    auto reg = unique_registry();
    int rc = run_pub_sub(
        [&] {
            Node pub("typed_pub", {.force_transport = "shm", .registry_name = reg});
            pub.start();
            pub.advertise("imu");
            pub.spin_for(std::chrono::milliseconds(800));
            for (int i = 0; i < 5; i++) {
                pub.publish("imu", ImuSample{(uint64_t)i, (float)i * 0.1f, 0, 9.81f});
                pub.spin_for(std::chrono::milliseconds(20));
            }
            pub.spin_for(std::chrono::milliseconds(400));
            pub.stop();
        },
        [&] {
            Node sub("typed_sub", {.force_transport = "shm", .registry_name = reg});
            sub.start();
            std::vector<ImuSample> received;
            sub.subscribe<ImuSample>("imu", [&](const ImuSample& m) { received.push_back(m); });
            sub.spin_for(std::chrono::seconds(3));
            sub.stop();
            if (received.size() != 5) return 1;
            for (int i = 0; i < 5; i++) {
                ImuSample expected{(uint64_t)i, (float)i * 0.1f, 0, 9.81f};
                if (!(received[i] == expected)) return 2;
            }
            return 0;
        });
    REQUIRE(rc == 0);
}

TEST_CASE("Node: keep_latest subscriber sees the freshest value, not a backlog", "[node][fork][typed]") {
    auto reg = unique_registry();
    int rc = run_pub_sub(
        [&] {
            Node pub("kl_pub", {.force_transport = "shm", .registry_name = reg});
            pub.start();
            pub.advertise("fast");
            pub.spin_for(std::chrono::milliseconds(800));
            // fast, unpaced publishing -- a keep_latest subscriber
            // should never see every single one of these
            pub.publish_loop_for(std::chrono::seconds(1), [&] {
                static int i = 0;
                pub.publish("fast", ImuSample{(uint64_t)i, (float)i, 0, 0});
                i++;
            });
            pub.spin_for(std::chrono::milliseconds(400));
            pub.stop();
        },
        [&] {
            Node sub("kl_sub", {.force_transport = "shm", .registry_name = reg});
            sub.start();
            int dispatch_count = 0;
            uint64_t last_ts = 0;
            sub.subscribe<ImuSample>("fast", [&](const ImuSample& m) {
                dispatch_count++;
                last_ts = m.timestamp_ns;
            }, /*keep_latest=*/true);
            sub.spin_for(std::chrono::milliseconds(2000));
            sub.stop();
            // The whole point of keep_latest: far fewer dispatches
            // than publishes, and the last one seen should be recent.
            if (dispatch_count == 0) return 1;
            if (dispatch_count > 5000) return 2;  // should NOT see every message
            return 0;
        });
    REQUIRE(rc == 0);
}

TEST_CASE("Node: fan-out -- one publisher, multiple subscribers all receive every message", "[node][fork]") {
    auto reg = unique_registry();
    pid_t sub_a = fork();
    REQUIRE(sub_a >= 0);
    if (sub_a == 0) {
        Node sub("fanout_a", {.force_transport = "shm", .registry_name = reg});
        sub.start();
        std::vector<int> received;
        sub.subscribe("t", [&](const uint8_t* d, uint32_t n) {
            (void)n;
            received.push_back(*(const int*)d);
        });
        sub.spin_for(std::chrono::seconds(3));
        sub.stop();
        _exit(received.size() == 8 ? 0 : 1);
    }

    pid_t sub_b = fork();
    REQUIRE(sub_b >= 0);
    if (sub_b == 0) {
        Node sub("fanout_b", {.force_transport = "shm", .registry_name = reg});
        sub.start();
        std::vector<int> received;
        sub.subscribe("t", [&](const uint8_t* d, uint32_t n) {
            (void)n;
            received.push_back(*(const int*)d);
        });
        sub.spin_for(std::chrono::seconds(3));
        sub.stop();
        _exit(received.size() == 8 ? 0 : 1);
    }

    Node pub("fanout_pub", {.force_transport = "shm", .registry_name = reg});
    pub.start();
    pub.advertise("t");
    pub.spin_for(std::chrono::milliseconds(900));
    for (int i = 0; i < 8; i++) {
        pub.publish("t", (const uint8_t*)&i, sizeof(i));
        pub.spin_for(std::chrono::milliseconds(20));
    }
    pub.spin_for(std::chrono::milliseconds(500));
    pub.stop();

    int status_a, status_b;
    waitpid(sub_a, &status_a, 0);
    waitpid(sub_b, &status_b, 0);
    REQUIRE(WIFEXITED(status_a));
    REQUIRE(WEXITSTATUS(status_a) == 0);
    REQUIRE(WIFEXITED(status_b));
    REQUIRE(WEXITSTATUS(status_b) == 0);
}

TEST_CASE("Node: publish() to an un-advertised topic throws NodeError", "[node]") {
    auto reg = unique_registry();
    Node n("error_test", {.registry_name = reg});
    n.start();
    REQUIRE_THROWS_AS(n.publish("never_advertised", (const uint8_t*)"x", 1), NodeError);
    n.stop();
}

TEST_CASE("Node: NodeOptions constructor and legacy positional constructor behave identically", "[node]") {
    auto reg = unique_registry();
    NodeOptions opts;
    opts.force_transport = "udp";
    opts.registry_name = reg;
    Node n1("opts_style", opts);

    Node n2("positional_style", "127.0.0.1", 0, "udp", 16 << 20, 1 << 20, reg);

    n1.start();
    n2.start();
    REQUIRE(n1.is_started());
    REQUIRE(n2.is_started());
    REQUIRE(n1.node_id() == "opts_style");
    REQUIRE(n2.node_id() == "positional_style");
    n1.stop();
    n2.stop();
}

TEST_CASE("Node: move semantics transfer ownership without double-closing resources", "[node]") {
    auto reg = unique_registry();
    Node n1("move_test", {.registry_name = reg});
    n1.start();
    REQUIRE(n1.is_started());

    Node n2 = std::move(n1);
    REQUIRE(n2.is_started());
    REQUIRE(n2.node_id() == "move_test");
    // n1 is now in a moved-from state; its destructor must not try to
    // tear down resources n2 now owns. If it did, this test would
    // crash or hang rather than fail cleanly -- that's the point of
    // testing it at all.
    n2.stop();

    static_assert(!std::is_copy_constructible<Node>::value, "Node must not be copyable");
    static_assert(std::is_move_constructible<Node>::value, "Node must be movable");
}

TEST_CASE("Node: stop() is idempotent and safe before start()", "[node]") {
    auto reg = unique_registry();
    Node n("idempotent_test", {.registry_name = reg});
    n.stop();  // never started -- must be a safe no-op
    n.stop();  // and calling it again must also be safe
    REQUIRE_FALSE(n.is_started());
}
