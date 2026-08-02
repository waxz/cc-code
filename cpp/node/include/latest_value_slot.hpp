// latest_value_slot.hpp
//
// Lock-free single-slot "latest value wins" shared memory primitive.
// Direct port of shared_memory_ipc.py's LatestValueSlot: a writer
// never blocks regardless of a slow or stalled reader (it just
// overwrites), and a reader always gets the most recent complete
// write via the classic seqlock pattern (odd sequence = write in
// progress, even = stable; reader retries if it observes an odd
// sequence or the sequence changes mid-copy).
//
// This is the primitive behind Node::subscribe(topic, cb, keep_latest
// = true) -- the C++ analogue of ROS2's "keep last 1" QoS depth, and
// the actual fix for the p99 latency investigation: it bounds
// staleness by construction instead of bounding queueing delay, which
// is a fundamentally different (and much stronger) guarantee under a
// publisher that outpaces its consumer.
#pragma once

#include <atomic>
#include <cstdint>
#include <cstring>
#include <chrono>
#include <stdexcept>
#include <string>
#include <thread>

#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

namespace commsys {

struct SlotHeader {
    std::atomic<uint64_t> seq;  // even = stable, odd = write in progress
    uint64_t capacity;
    uint8_t closed;
};

class LatestValueSlot {
public:
    static LatestValueSlot create(const std::string& name, uint64_t capacity) {
        shm_unlink(name.c_str());
        size_t total = sizeof(SlotHeader) + 4 + capacity;  // +4 for payload length prefix
        int fd = shm_open(name.c_str(), O_CREAT | O_EXCL | O_RDWR, 0666);
        if (fd < 0) throw std::runtime_error("shm_open create failed: " + name);
        if (ftruncate(fd, (off_t)total) != 0) { close(fd); throw std::runtime_error("ftruncate failed"); }
        void* base = mmap(nullptr, total, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
        close(fd);
        if (base == MAP_FAILED) throw std::runtime_error("mmap failed: " + name);

        LatestValueSlot s;
        s.base_ = base; s.total_size_ = total;
        s.hdr_ = reinterpret_cast<SlotHeader*>(base);
        s.data_ = reinterpret_cast<uint8_t*>(base) + sizeof(SlotHeader);
        s.capacity_ = capacity; s.owns_ = true; s.name_ = name;
        s.hdr_->seq.store(0);
        s.hdr_->capacity = capacity;
        s.hdr_->closed = 0;
        return s;
    }

    static LatestValueSlot attach(const std::string& name, double timeout_sec = 2.0) {
        auto deadline = std::chrono::steady_clock::now() +
                         std::chrono::duration<double>(timeout_sec);
        int fd = -1;
        while (std::chrono::steady_clock::now() < deadline) {
            fd = shm_open(name.c_str(), O_RDWR, 0666);
            if (fd >= 0) break;
            std::this_thread::sleep_for(std::chrono::milliseconds(5));
        }
        if (fd < 0) throw std::runtime_error("shm_open attach failed: " + name);

        struct stat st;
        while (std::chrono::steady_clock::now() < deadline) {
            if (fstat(fd, &st) == 0 && st.st_size >= (off_t)sizeof(SlotHeader)) break;
            std::this_thread::sleep_for(std::chrono::milliseconds(2));
        }

        void* peek = mmap(nullptr, sizeof(SlotHeader), PROT_READ, MAP_SHARED, fd, 0);
        if (peek == MAP_FAILED) { close(fd); throw std::runtime_error("mmap peek failed"); }
        uint64_t capacity = 0;
        while (std::chrono::steady_clock::now() < deadline) {
            capacity = reinterpret_cast<SlotHeader*>(peek)->capacity;
            if (capacity != 0) break;
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
        munmap(peek, sizeof(SlotHeader));
        if (capacity == 0) { close(fd); throw std::runtime_error("header never initialized: " + name); }

        size_t total = sizeof(SlotHeader) + 4 + capacity;
        void* base = mmap(nullptr, total, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
        close(fd);
        if (base == MAP_FAILED) throw std::runtime_error("mmap full failed: " + name);

        LatestValueSlot s;
        s.base_ = base; s.total_size_ = total;
        s.hdr_ = reinterpret_cast<SlotHeader*>(base);
        s.data_ = reinterpret_cast<uint8_t*>(base) + sizeof(SlotHeader);
        s.capacity_ = capacity; s.owns_ = false; s.name_ = name;
        return s;
    }

    LatestValueSlot() = default;
    LatestValueSlot(LatestValueSlot&& other) noexcept { *this = std::move(other); }
    LatestValueSlot& operator=(LatestValueSlot&& other) noexcept {
        if (this != &other) {
            release();
            base_ = other.base_; total_size_ = other.total_size_;
            hdr_ = other.hdr_; data_ = other.data_; capacity_ = other.capacity_;
            owns_ = other.owns_; name_ = std::move(other.name_);
            other.base_ = nullptr; other.hdr_ = nullptr; other.data_ = nullptr;
        }
        return *this;
    }
    LatestValueSlot(const LatestValueSlot&) = delete;
    LatestValueSlot& operator=(const LatestValueSlot&) = delete;
    ~LatestValueSlot() { release(); }

    void mark_closed() { if (hdr_) hdr_->closed = 1; }
    bool is_closed() const { return hdr_ && hdr_->closed == 1; }

    void write(const uint8_t* payload, uint32_t len) {
        if (len + 4 > capacity_) throw std::runtime_error("payload larger than slot capacity");
        uint64_t seq = hdr_->seq.load(std::memory_order_relaxed);
        hdr_->seq.store(seq + 1, std::memory_order_release);  // odd: write in progress
        memcpy(data_, &len, 4);
        memcpy(data_ + 4, payload, len);
        hdr_->seq.store(seq + 2, std::memory_order_release);  // even: stable
    }

    // Returns length read into out, or -1 if nothing written yet / a
    // persistent race prevented a clean read within bounded retries.
    int try_read(uint8_t* out) {
        uint64_t seq;
        return try_read_versioned(out, seq);
    }

    // Same as try_read, but also reports the seqlock's internal
    // version counter at the moment of the successful read, so a
    // caller can cheaply detect "nothing new since I last looked"
    // (compare one integer) instead of either re-dispatching every
    // poll regardless of whether the value actually changed, or doing
    // a full byte-for-byte comparison of a potentially large payload.
    int try_read_versioned(uint8_t* out, uint64_t& out_seq) {
        for (int attempt = 0; attempt < 50; attempt++) {
            uint64_t s1 = hdr_->seq.load(std::memory_order_acquire);
            if (s1 & 1) continue;  // writer mid-update
            uint32_t len;
            memcpy(&len, data_, 4);
            if (len == 0) return -1;
            memcpy(out, data_ + 4, len);
            uint64_t s2 = hdr_->seq.load(std::memory_order_acquire);
            if (s1 == s2) { out_seq = s1; return (int)len; }
            // torn read (a write raced us); retry
        }
        return -1;
    }

    uint64_t capacity() const { return capacity_; }

private:
    void release() {
        if (base_) munmap(base_, total_size_);
        if (owns_ && !name_.empty()) shm_unlink(name_.c_str());
        base_ = nullptr;
    }

    void* base_ = nullptr;
    size_t total_size_ = 0;
    SlotHeader* hdr_ = nullptr;
    uint8_t* data_ = nullptr;
    uint64_t capacity_ = 0;
    bool owns_ = false;
    std::string name_;
};

}  // namespace commsys
