// bench_ringbuffer.cpp
// Cross-process SPSC ring buffer over POSIX shared memory, same
// design as shared_memory_ipc.py (doubled-modulus indices, spin/yield
// backoff), benchmarked the same way as test_shm.py: fork a producer,
// have the parent consume, time until all messages are received.
#include <atomic>
#include <cstdint>
#include <cstring>
#include <cstdio>
#include <chrono>
#include <thread>
#include <fcntl.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>

struct RingHeader {
    std::atomic<uint64_t> write_idx;
    std::atomic<uint64_t> read_idx;
    uint64_t capacity;
    uint8_t closed;
};

class RingBuffer {
public:
    RingBuffer(uint8_t* base, uint64_t capacity)
        : hdr_(reinterpret_cast<RingHeader*>(base)),
          data_(base + sizeof(RingHeader)),
          capacity_(capacity) {}

    void init() {
        hdr_->write_idx.store(0);
        hdr_->read_idx.store(0);
        hdr_->capacity = capacity_;
        hdr_->closed = 0;
    }

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

    // returns length written into out, or -1 if empty
    int try_read(uint8_t* out, uint32_t out_cap) {
        uint64_t w = hdr_->write_idx.load(std::memory_order_acquire);
        uint64_t r = hdr_->read_idx.load(std::memory_order_relaxed);
        if (w == r) return -1;
        uint32_t len;
        read_bytes(r, reinterpret_cast<uint8_t*>(&len), 4);
        read_bytes(r + 4, out, len);
        hdr_->read_idx.store((r + 4 + len) % (2 * capacity_), std::memory_order_release);
        return (int)len;
    }

    void mark_closed() { hdr_->closed = 1; }
    bool is_closed() const { return hdr_->closed == 1; }

private:
    void write_bytes(uint64_t pos, const uint8_t* data, uint32_t n) {
        pos %= capacity_;
        if (pos + n <= capacity_) {
            std::memcpy(data_ + pos, data, n);
        } else {
            uint32_t first = capacity_ - pos;
            std::memcpy(data_ + pos, data, first);
            std::memcpy(data_, data + first, n - first);
        }
    }
    void read_bytes(uint64_t pos, uint8_t* out, uint32_t n) {
        pos %= capacity_;
        if (pos + n <= capacity_) {
            std::memcpy(out, data_ + pos, n);
        } else {
            uint32_t first = capacity_ - pos;
            std::memcpy(out, data_ + pos, first);
            std::memcpy(out + first, data_, n - first);
        }
    }

    RingHeader* hdr_;
    uint8_t* data_;
    uint64_t capacity_;
};

int main() {
    const uint64_t CAPACITY = 1 << 20;
    const size_t TOTAL = sizeof(RingHeader) + CAPACITY;
    const int N = 500000;  // messages, matching the scale of the Python cross-process test but larger for a stable measurement

    int fd = shm_open("/cpp_bench_ring", O_CREAT | O_RDWR, 0666);
    ftruncate(fd, TOTAL);
    uint8_t* base = (uint8_t*)mmap(nullptr, TOTAL, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);

    RingBuffer ring(base, CAPACITY);
    ring.init();

    pid_t pid = fork();
    if (pid == 0) {
        // child = producer
        int fd2 = shm_open("/cpp_bench_ring", O_RDWR, 0666);
        uint8_t* base2 = (uint8_t*)mmap(nullptr, TOTAL, PROT_READ | PROT_WRITE, MAP_SHARED, fd2, 0);
        RingBuffer prod(base2, CAPACITY);
        int64_t payload;
        for (int i = 0; i < N; i++) {
            payload = i;
            while (!prod.try_write(reinterpret_cast<uint8_t*>(&payload), sizeof(payload))) {
                std::this_thread::yield();
            }
        }
        prod.mark_closed();
        _exit(0);
    }

    // parent = consumer
    uint8_t out[64];
    int received = 0;
    auto t0 = std::chrono::high_resolution_clock::now();
    while (received < N) {
        int n = ring.try_read(out, sizeof(out));
        if (n < 0) {
            if (ring.is_closed()) break;
            std::this_thread::yield();
            continue;
        }
        received++;
    }
    auto t1 = std::chrono::high_resolution_clock::now();
    waitpid(pid, nullptr, 0);

    double secs = std::chrono::duration<double>(t1 - t0).count();
    printf("=== C++ SPSC ring buffer, cross-process (fork), N=%d ===\n", N);
    printf("  received %d messages in %.4fs  (%.0f msg/s)\n", received, secs, received / secs);

    munmap(base, TOTAL);
    shm_unlink("/cpp_bench_ring");
    return 0;
}
