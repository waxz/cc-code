// bench_tcc_jit.c
// Demonstrates libtcc's headline feature: compiling a C function from
// a string, entirely in memory, and calling it -- no separate compile
// step, no file I/O, no linker invocation. This is what you'd embed
// in a host process (Python via a thin ctypes/cffi shim, or directly
// from C/C++) to JIT-compile small snippets at runtime.
#include <libtcc.h>
#include <stdio.h>
#include <time.h>

static double now_sec(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}

const char* SRC =
    "float imu_sum_az(float* az_values, int n) {"
    "    float total = 0;"
    "    for (int i = 0; i < n; i++) total += az_values[i];"
    "    return total;"
    "}";

int main(void) {
    float az[20];
    for (int i = 0; i < 20; i++) az[i] = 9.81f;

    double t0 = now_sec();
    TCCState* s = tcc_new();
    tcc_set_output_type(s, TCC_OUTPUT_MEMORY);
    tcc_compile_string(s, SRC);
    int mem_size = tcc_relocate(s, NULL);
    void* mem = malloc(mem_size);
    tcc_relocate(s, mem);
    typedef float (*imu_sum_fn)(float*, int);
    imu_sum_fn fn = (imu_sum_fn)tcc_get_symbol(s, "imu_sum_az");
    double t1 = now_sec();

    float result = fn(az, 20);
    double t2 = now_sec();

    printf("compile+link+resolve: %.3fms\n", (t1 - t0) * 1000);
    printf("first call:           %.3fus, result=%.2f\n", (t2 - t1) * 1e6, result);

    // subsequent calls to the JIT-compiled function, once already resolved
    double t3 = now_sec();
    volatile float sink = 0;
    for (int i = 0; i < 1000000; i++) sink = fn(az, 20);
    double t4 = now_sec();
    printf("1M subsequent calls:  %.4fs (%.1fns/call)\n", t4 - t3, (t4 - t3) * 1e9 / 1000000);

    tcc_delete(s);
    return 0;
}
