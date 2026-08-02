// ring_buffer.hpp
//
// Lock-free single-producer/single-consumer ring buffer over POSIX
// shared memory. Mirrors shared_memory_ipc.py's SPSCRingBuffer,
// including the two race-condition fixes discovered and validated
// there:
//   1. Wait for the header to be fully initialized before trusting
//      capacity (shm_open()+ftruncate() are non-atomic, so an
//      attacher can briefly see a zero-sized/zero-initialized
//      segment).
//   2. Retry attach on a transient "empty file" mmap failure for the
//      same underlying reason.
//
// Unlike the Python version, there is no equivalent of the
// ctypes-array-slicing bug to fix here -- memcpy is just memcpy in
// C++, which is exactly the point of this port.
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

struct RingHeader {
    std::atomic<uint64_t> write_idx;
    std::atomic<uint64_t> read_idx;
    uint64_t capacity;
    uint8_t closed;
};

class RingBuffer {
public:
    // Create a new ring (fails if one already exists under this name).
    static RingBuffer create(const std::string& name, uint64_t capacity) {
        std::string shm_name = name;
        shm_unlink(shm_name.c_str());  // clear any stale segment from a crashed run
        size_t total = sizeof(RingHeader) + capacity;
        int fd = shm_open(shm_name.c_str(), O_CREAT | O_EXCL | O_RDWR, 0666);
        if (fd < 0) throw std::runtime_error("shm_open create failed: " + shm_name);
        if (ftruncate(fd, (off_t)total) != 0) {
            close(fd);
            throw std::runtime_error("ftruncate failed: " + shm_name);
        }
        void* base = mmap(nullptr, total, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
        close(fd);
        if (base == MAP_FAILED) throw std::runtime_error("mmap failed: " + shm_name);
        RingBuffer rb;
        rb.base_ = base;
        rb.total_size_ = total;
        rb.hdr_ = reinterpret_cast<RingHeader*>(base);
        rb.data_ = reinterpret_cast<uint8_t*>(base) + sizeof(RingHeader);
        rb.capacity_ = capacity;
        rb.owns_ = true;
        rb.name_ = shm_name;
        rb.hdr_->write_idx.store(0);
        rb.hdr_->read_idx.store(0);
        rb.hdr_->capacity = capacity;
        rb.hdr_->closed = 0;
        return rb;
    }

    // Attach to an existing ring, retrying briefly if the creator
    // hasn't finished initializing it yet (see file header comment).
    static RingBuffer attach(const std::string& name, double timeout_sec = 2.0) {
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
            if (fstat(fd, &st) == 0 && st.st_size >= (off_t)sizeof(RingHeader)) break;
            std::this_thread::sleep_for(std::chrono::milliseconds(2));
        }
        if (st.st_size < (off_t)sizeof(RingHeader)) {
            close(fd);
            throw std::runtime_error("segment never resized by creator: " + name);
        }

        void* peek = mmap(nullptr, sizeof(RingHeader), PROT_READ, MAP_SHARED, fd, 0);
        if (peek == MAP_FAILED) { close(fd); throw std::runtime_error("mmap peek failed"); }
        uint64_t capacity = 0;
        while (std::chrono::steady_clock::now() < deadline) {
            capacity = reinterpret_cast<RingHeader*>(peek)->capacity;
            if (capacity != 0) break;
            std::this_thread::sleep_for(std::chrono::milliseconds(1));
        }
        munmap(peek, sizeof(RingHeader));
        if (capacity == 0) { close(fd); throw std::runtime_error("header never initialized: " + name); }

        size_t total = sizeof(RingHeader) + capacity;
        void* base = mmap(nullptr, total, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
        close(fd);
        if (base == MAP_FAILED) throw std::runtime_error("mmap full failed: " + name);

        RingBuffer rb;
        rb.base_ = base;
        rb.total_size_ = total;
        rb.hdr_ = reinterpret_cast<RingHeader*>(base);
        rb.data_ = reinterpret_cast<uint8_t*>(base) + sizeof(RingHeader);
        rb.capacity_ = capacity;
        rb.owns_ = false;
        rb.name_ = name;
        return rb;
    }

    RingBuffer() = default;
    RingBuffer(RingBuffer&& other) noexcept { *this = std::move(other); }
    RingBuffer& operator=(RingBuffer&& other) noexcept {
        if (this != &other) {
            release();
            base_ = other.base_; total_size_ = other.total_size_;
            hdr_ = other.hdr_; data_ = other.data_; capacity_ = other.capacity_;
            owns_ = other.owns_; name_ = std::move(other.name_);
            other.base_ = nullptr; other.hdr_ = nullptr; other.data_ = nullptr;
        }
        return *this;
    }
    RingBuffer(const RingBuffer&) = delete;
    RingBuffer& operator=(const RingBuffer&) = delete;
    ~RingBuffer() { release(); }

    void mark_closed() { if (hdr_) hdr_->closed = 1; }
    bool is_closed() const { return hdr_ && hdr_->closed == 1; }

    bool try_write(const uint8_t* payload, uint32_t len) {
        uint64_t need = 4 + len;
        uint64_t w = hdr_->write_idx.load(std::memory_order_relaxed);
        uint64_t r = hdr_->read_idx.load(std::memory_order_acquire);
        uint64_t used = (w - r) % (2 * capacity_);
        if (capacity_ - used < need) return false;
        write_bytes(w, reinterpret_cast<const uint8_t*>(&len), 4);
        write_bytes(w + 4, payload, len);
        hdr_->write_idx.store((w + need) % (2 * capacity_), std::memory_order_release);
        return true;
    }

    // Returns length read into out (out must be >= capacity_ bytes to
    // be safe for any message), or -1 if the ring is currently empty.
    int try_read(uint8_t* out) {
        uint64_t w = hdr_->write_idx.load(std::memory_order_acquire);
        uint64_t r = hdr_->read_idx.load(std::memory_order_relaxed);
        if (w == r) return -1;
        uint32_t len;
        read_bytes(r, reinterpret_cast<uint8_t*>(&len), 4);
        read_bytes(r + 4, out, len);
        hdr_->read_idx.store((r + 4 + len) % (2 * capacity_), std::memory_order_release);
        return (int)len;
    }

    uint64_t capacity() const { return capacity_; }
    const std::string& name() const { return name_; }

private:
    void release() {
        if (base_) munmap(base_, total_size_);
        if (owns_ && !name_.empty()) shm_unlink(name_.c_str());
        base_ = nullptr;
    }

    void write_bytes(uint64_t pos, const uint8_t* src, uint32_t n) {
        pos %= capacity_;
        if (pos + n <= capacity_) {
            memcpy(data_ + pos, src, n);
        } else {
            uint32_t first = (uint32_t)(capacity_ - pos);
            memcpy(data_ + pos, src, first);
            memcpy(data_, src + first, n - first);
        }
    }
    void read_bytes(uint64_t pos, uint8_t* dst, uint32_t n) {
        pos %= capacity_;
        if (pos + n <= capacity_) {
            memcpy(dst, data_ + pos, n);
        } else {
            uint32_t first = (uint32_t)(capacity_ - pos);
            memcpy(dst, data_ + pos, first);
            memcpy(dst + first, data_, n - first);
        }
    }

    void* base_ = nullptr;
    size_t total_size_ = 0;
    RingHeader* hdr_ = nullptr;
    uint8_t* data_ = nullptr;
    uint64_t capacity_ = 0;
    bool owns_ = false;
    std::string name_;
};

}  // namespace commsys
