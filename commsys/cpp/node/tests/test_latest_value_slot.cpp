#include <catch2/catch_all.hpp>
#include "../include/latest_value_slot.hpp"
#include <unistd.h>
#include <sys/wait.h>
#include <cstring>
#include <chrono>
#include <random>

using namespace commsys;

namespace {
std::string unique_name(const char* prefix) {
    static std::mt19937 rng(std::random_device{}());
    return std::string("/") + prefix + "_" + std::to_string(rng()) + "_" + std::to_string(getpid());
}
}  // namespace

TEST_CASE("LatestValueSlot: read before any write returns -1 (nothing yet)", "[latest_value_slot]") {
    auto name = unique_name("lvs_empty");
    auto slot = LatestValueSlot::create(name, 4096);
    uint8_t out[64];
    REQUIRE(slot.try_read(out) == -1);
}

TEST_CASE("LatestValueSlot: single write then read", "[latest_value_slot]") {
    auto name = unique_name("lvs_basic");
    auto slot = LatestValueSlot::create(name, 4096);

    slot.write((const uint8_t*)"hello", 5);
    uint8_t out[64];
    int n = slot.try_read(out);
    REQUIRE(n == 5);
    REQUIRE(std::memcmp(out, "hello", 5) == 0);
}

TEST_CASE("LatestValueSlot: repeated reads return the same value until overwritten", "[latest_value_slot]") {
    auto name = unique_name("lvs_repeat");
    auto slot = LatestValueSlot::create(name, 4096);
    uint8_t out[64];

    slot.write((const uint8_t*)"first", 5);
    REQUIRE(slot.try_read(out) == 5);
    REQUIRE(std::memcmp(out, "first", 5) == 0);
    // reading again without a new write gives the same value, not "nothing new"
    REQUIRE(slot.try_read(out) == 5);
    REQUIRE(std::memcmp(out, "first", 5) == 0);

    slot.write((const uint8_t*)"second-value", 12);
    REQUIRE(slot.try_read(out) == 12);
    REQUIRE(std::memcmp(out, "second-value", 12) == 0);
}

TEST_CASE("LatestValueSlot: writer never blocks even with no reader present", "[latest_value_slot]") {
    // The entire point of this primitive: a slow/absent reader must
    // never cause the writer to stall.
    auto name = unique_name("lvs_noblock");
    auto slot = LatestValueSlot::create(name, 1024);

    auto t0 = std::chrono::steady_clock::now();
    for (int i = 0; i < 20000; i++) {
        std::string msg = "m" + std::to_string(i);
        slot.write((const uint8_t*)msg.data(), (uint32_t)msg.size());
    }
    auto dt = std::chrono::duration<double>(std::chrono::steady_clock::now() - t0).count();
    REQUIRE(dt < 1.0);  // 20k writes with zero readers must not take anywhere near this long

    uint8_t out[64];
    int n = slot.try_read(out);
    REQUIRE(n > 0);
    REQUIRE(std::string((char*)out, n) == "m19999");
}

TEST_CASE("LatestValueSlot: payload larger than capacity throws", "[latest_value_slot]") {
    auto name = unique_name("lvs_toolarge");
    auto slot = LatestValueSlot::create(name, 16);
    std::vector<uint8_t> big(1000, 0);
    REQUIRE_THROWS(slot.write(big.data(), (uint32_t)big.size()));
}

TEST_CASE("LatestValueSlot: is_closed()/mark_closed()", "[latest_value_slot]") {
    auto name = unique_name("lvs_close");
    auto slot = LatestValueSlot::create(name, 4096);
    REQUIRE_FALSE(slot.is_closed());
    slot.mark_closed();
    REQUIRE(slot.is_closed());
}

TEST_CASE("LatestValueSlot: cross-process reader always sees a recent, non-torn value", "[latest_value_slot][fork]") {
    // A slow/late reader should see *some* valid, complete value from
    // near the end of a fast writer's run -- never garbage, and never
    // forced to work through a backlog to get there.
    auto name = unique_name("lvs_crossproc");
    auto slot = LatestValueSlot::create(name, 4096);

    pid_t pid = fork();
    REQUIRE(pid >= 0);
    if (pid == 0) {
        auto writer = LatestValueSlot::attach(name);
        for (int i = 0; i < 5000; i++) {
            std::string msg = "msg-" + std::to_string(i);
            writer.write((const uint8_t*)msg.data(), (uint32_t)msg.size());
        }
        _exit(0);
    }
    usleep(300000);  // let the writer race far ahead

    uint8_t out[64];
    int n = slot.try_read(out);
    REQUIRE(n > 0);
    std::string val((char*)out, n);
    REQUIRE(val.rfind("msg-", 0) == 0);
    int idx = std::stoi(val.substr(4));
    REQUIRE(idx > 2000);  // should be recent, not stuck near the start

    int status;
    waitpid(pid, &status, 0);
    REQUIRE(WIFEXITED(status));
}

TEST_CASE("LatestValueSlot: seqlock never returns a torn/corrupted value under concurrent write+read", "[latest_value_slot][fork]") {
    auto name = unique_name("lvs_torn");
    auto slot = LatestValueSlot::create(name, 4096);

    const int N = 3000;
    std::set<std::string> valid;
    for (int i = 0; i < N; i++) valid.insert("payload-" + std::to_string(i));

    pid_t pid = fork();
    REQUIRE(pid >= 0);
    if (pid == 0) {
        auto writer = LatestValueSlot::attach(name);
        for (int i = 0; i < N; i++) {
            std::string msg = "payload-" + std::to_string(i);
            writer.write((const uint8_t*)msg.data(), (uint32_t)msg.size());
        }
        _exit(0);
    }

    bool any_torn = false;
    for (int i = 0; i < 5000; i++) {
        uint8_t out[64];
        int n = slot.try_read(out);
        if (n > 0) {
            std::string val((char*)out, n);
            if (!valid.count(val)) { any_torn = true; break; }
        }
    }
    REQUIRE_FALSE(any_torn);

    int status;
    waitpid(pid, &status, 0);
}

TEST_CASE("LatestValueSlot: move semantics transfer ownership correctly", "[latest_value_slot]") {
    auto name = unique_name("lvs_move");
    auto slot1 = LatestValueSlot::create(name, 4096);
    slot1.write((const uint8_t*)"before-move", 11);

    LatestValueSlot slot2 = std::move(slot1);
    uint8_t out[64];
    int n = slot2.try_read(out);
    REQUIRE(n == 11);
    REQUIRE(std::memcmp(out, "before-move", 11) == 0);

    static_assert(!std::is_copy_constructible<LatestValueSlot>::value, "LatestValueSlot must not be copyable");
    static_assert(std::is_move_constructible<LatestValueSlot>::value, "LatestValueSlot must be movable");
}
