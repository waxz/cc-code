// bench_udp_raw.cpp
// Raw UDP send throughput on loopback, no reliability/ACK layer --
// isolates the syscall-bound floor that Python's asyncio event loop
// also has to pay, to show where C++'s advantage shrinks.
#include <cstdio>
#include <cstring>
#include <chrono>
#include <arpa/inet.h>
#include <unistd.h>
#include <sys/socket.h>

int main() {
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(23456);
    inet_pton(AF_INET, "127.0.0.1", &addr.sin_addr);

    const int N = 200000;
    char payload[64] = "x";
    memset(payload, 'x', sizeof(payload));

    auto t0 = std::chrono::high_resolution_clock::now();
    for (int i = 0; i < N; i++) {
        sendto(sock, payload, sizeof(payload), 0, (sockaddr*)&addr, sizeof(addr));
    }
    auto t1 = std::chrono::high_resolution_clock::now();
    double secs = std::chrono::duration<double>(t1 - t0).count();
    printf("=== C++ raw UDP sendto(), no receiver, N=%d ===\n", N);
    printf("  %.4fs total, %.0f sendto/s, %.0fns/call\n",
           secs, N / secs, secs * 1e9 / N);
    close(sock);
    return 0;
}
