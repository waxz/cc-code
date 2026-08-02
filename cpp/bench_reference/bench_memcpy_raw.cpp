#include <cstdio>
#include <cstring>
#include <chrono>
#include <vector>
int main() {
    const size_t SIZE = 256ull << 20; // 256MB buffers
    std::vector<uint8_t> src(SIZE, 1), dst(SIZE, 0);
    const int N = 40;
    auto t0 = std::chrono::high_resolution_clock::now();
    for (int i = 0; i < N; i++) memcpy(dst.data(), src.data(), SIZE);
    auto t1 = std::chrono::high_resolution_clock::now();
    double secs = std::chrono::duration<double>(t1 - t0).count();
    printf("single-thread memcpy: %.3f GB/s\n", (N * (double)SIZE / secs) / 1e9);
}
