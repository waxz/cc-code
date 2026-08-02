// bench_struct.c
// Plain C (not C++ -- TCC doesn't support C++) version of the raw IMU
// struct pack/unpack loop, for a fair tcc-vs-gcc comparison of both
// compile time and generated-code speed.
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <time.h>

#pragma pack(push, 1)
typedef struct {
    uint64_t timestamp_ns;
    float ax, ay, az;
    float gx, gy, gz;
} ImuSampleRaw;
#pragma pack(pop)

static double now_sec(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}

int main(void) {
    const int N = 20;
    const int ITERS = 2000000;
    ImuSampleRaw samples[20];
    for (int i = 0; i < N; i++) {
        samples[i].timestamp_ns = i;
        samples[i].ax = 0.1f; samples[i].ay = 0.2f; samples[i].az = 9.81f;
        samples[i].gx = 0.01f; samples[i].gy = 0.02f; samples[i].gz = 0.03f;
    }
    uint8_t buf[20 * sizeof(ImuSampleRaw)];

    double t0 = now_sec();
    volatile float sink = 0;
    for (int iter = 0; iter < ITERS; iter++) {
        memcpy(buf, samples, sizeof(buf));
        ImuSampleRaw* p = (ImuSampleRaw*)buf;
        float total = 0;
        for (int i = 0; i < N; i++) total += p[i].az;
        sink = total;
    }
    double t1 = now_sec();
    double secs = t1 - t0;
    printf("pack+unpack+sum loop: %d iters in %.4fs -> %.1fns/iter (%.0f iters/s)\n",
           ITERS, secs, secs * 1e9 / ITERS, ITERS / secs);
    return 0;
}
