#include <catch2/catch_all.hpp>
#include "../include/ring_buffer.hpp"
#include "test_helpers.hpp"
#include <unistd.h>
#include <sys/wait.h>
#include <cstring>

using namespace commsys;
using commsys_test::ChildProcess;
using commsys_test::unique_name;

TEST_CASE("RingBuffer: single write/read round-trip in one process", "[ring_buffer]") {
    auto name = unique_name("rb_basic");
    auto ring = RingBuffer::create(name, 4096);

    const char* msg = "hello";
    REQUIRE(ring.try_write((const uint8_t*)msg, 5));

    uint8_t out[64];
    int n = ring.try_read(out);
    REQUIRE(n == 5);
    REQUIRE(std::memcmp(out, msg, 5) == 0);

    // ring is now empty
    REQUIRE(ring.try_read(out) == -1);
}

TEST_CASE("RingBuffer: FIFO order preserved across many messages", "[ring_buffer]") {
    auto name = unique_name("rb_fifo");
    auto ring = RingBuffer::create(name, 65536);

    for (int i = 0; i < 200; i++) {
        std::string msg = "msg-" + std::to_string(i);
        REQUIRE(ring.try_write((const uint8_t*)msg.data(), (uint32_t)msg.size()));
    }
    for (int i = 0; i < 200; i++) {
        uint8_t out[64];
        int n = ring.try_read(out);
        std::string expected = "msg-" + std::to_string(i);
        REQUIRE(n == (int)expected.size());
        REQUIRE(std::memcmp(out, expected.data(), n) == 0);
    }
}

TEST_CASE("RingBuffer: wraparound correctness with a small capacity", "[ring_buffer]") {
    // Small enough that repeated writes/reads force the ring to wrap
    // past the physical end of its data region multiple times,
    // exercising the two-piece copy path in write_bytes/read_bytes.
    auto name = unique_name("rb_wrap");
    auto ring = RingBuffer::create(name, 64);

    for (int round = 0; round < 50; round++) {
        std::string msg = "r" + std::to_string(round % 10);
        REQUIRE(ring.try_write((const uint8_t*)msg.data(), (uint32_t)msg.size()));
        uint8_t out[64];
        int n = ring.try_read(out);
        REQUIRE(n == (int)msg.size());
        REQUIRE(std::memcmp(out, msg.data(), n) == 0);
    }
}

TEST_CASE("RingBuffer: try_write returns false when the ring is full", "[ring_buffer]") {
    auto name = unique_name("rb_full");
    auto ring = RingBuffer::create(name, 32);  // tiny, fills fast

    int successful = 0;
    while (ring.try_write((const uint8_t*)"x", 1)) {
        successful++;
        REQUIRE(successful < 1000);  // sanity bound, shouldn't ever get close
    }
    REQUIRE(successful > 0);

    // draining one message must free exactly enough space for one more
    uint8_t out[8];
    REQUIRE(ring.try_read(out) == 1);
    REQUIRE(ring.try_write((const uint8_t*)"y", 1));
}

TEST_CASE("RingBuffer: is_closed()/mark_closed()", "[ring_buffer]") {
    auto name = unique_name("rb_close");
    auto ring = RingBuffer::create(name, 4096);
    REQUIRE_FALSE(ring.is_closed());
    ring.mark_closed();
    REQUIRE(ring.is_closed());
}

TEST_CASE("RingBuffer: cross-process producer/consumer via fork", "[ring_buffer][fork]") {
    auto name = unique_name("rb_fork");
    auto ring = RingBuffer::create(name, 1 << 16);

    const int N = 500;
    pid_t pid = fork();
    REQUIRE(pid >= 0);
    if (pid == 0) {
        auto producer = RingBuffer::attach(name);
        for (int i = 0; i < N; i++) {
            std::string msg = "cp-" + std::to_string(i);
            while (!producer.try_write((const uint8_t*)msg.data(), (uint32_t)msg.size())) {
                usleep(100);
            }
        }
        _exit(0);
    }
    ChildProcess child(pid);

    int received = 0;
    while (received < N) {
        uint8_t out[64];
        int n = ring.try_read(out);
        if (n < 0) { usleep(100); continue; }
        std::string expected = "cp-" + std::to_string(received);
        REQUIRE(n == (int)expected.size());
        REQUIRE(std::memcmp(out, expected.data(), n) == 0);
        received++;
    }
    REQUIRE(child.wait() == 0);
}

TEST_CASE("RingBuffer: move semantics transfer ownership correctly", "[ring_buffer]") {
    auto name = unique_name("rb_move");
    auto ring1 = RingBuffer::create(name, 4096);
    REQUIRE(ring1.try_write((const uint8_t*)"before-move", 11));

    RingBuffer ring2 = std::move(ring1);
    uint8_t out[64];
    int n = ring2.try_read(out);
    REQUIRE(n == 11);
    REQUIRE(std::memcmp(out, "before-move", 11) == 0);

    static_assert(!std::is_copy_constructible<RingBuffer>::value, "RingBuffer must not be copyable");
    static_assert(std::is_move_constructible<RingBuffer>::value, "RingBuffer must be movable");
}

TEST_CASE("RingBuffer: attach retries and succeeds once the creator finishes", "[ring_buffer][fork]") {
    // Regression test for the real SIGBUS race documented in
    // ring_buffer.hpp: an attacher must wait for the creator's
    // ftruncate() to actually complete, not just for the name to
    // exist. Forking a child that attaches immediately, while the
    // parent creates with an artificial delay, exercises exactly
    // that race on every run rather than relying on scheduling luck.
    auto name = unique_name("rb_race");
    shm_unlink(name.c_str());

    pid_t pid = fork();
    REQUIRE(pid >= 0);
    if (pid == 0) {
        try {
            auto ring = RingBuffer::attach(name, 2.0);
            _exit(ring.capacity() == 8192 ? 0 : 1);
        } catch (...) {
            _exit(2);
        }
    }
    ChildProcess child(pid);
    usleep(20000);  // give the child's attach() a head start on the race
    auto ring = RingBuffer::create(name, 8192);

    REQUIRE(child.wait() == 0);
}
