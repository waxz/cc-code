cmake_minimum_required(VERSION 3.16)

# These are the standalone, single-file microbenchmarks used earlier
# in the project to decide whether porting to C++ was worth it before
# committing to the full node/ port -- kept as a reference/regression
# suite, not because anything here depends on them.

add_executable(bench_memcpy_raw bench_memcpy_raw.cpp)

add_executable(bench_ringbuffer bench_ringbuffer.cpp)
target_link_libraries(bench_ringbuffer PRIVATE rt Threads::Threads)

add_executable(bench_ringbuffer_large bench_ringbuffer_large.cpp)
target_link_libraries(bench_ringbuffer_large PRIVATE rt Threads::Threads)

add_executable(bench_struct_cpp bench_struct.cpp)

add_executable(bench_udp_raw bench_udp_raw.cpp)

add_executable(bench_struct_c bench_struct.c)
set_target_properties(bench_struct_c PROPERTIES OUTPUT_NAME bench_struct_c)

# FlatBuffers: optional. Only build the FlatBuffers microbenchmark if
# the system headers are actually installed (apt install
# libflatbuffers-dev flatbuffers-compiler) -- don't fail the whole
# build over an optional comparison point.
find_path(FLATBUFFERS_INCLUDE_DIR flatbuffers/flatbuffers.h)
if(FLATBUFFERS_INCLUDE_DIR)
  add_executable(bench_flatbuffers bench_flatbuffers.cpp)
  target_include_directories(bench_flatbuffers PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})
  message(STATUS "flatbuffers found -- building bench_flatbuffers")
else()
  message(STATUS "flatbuffers not found (apt install libflatbuffers-dev flatbuffers-compiler) -- skipping bench_flatbuffers")
endif()

# libtcc: optional, same reasoning -- this is the Tiny C Compiler JIT
# demo, not something the rest of the project depends on.
find_library(TCC_LIBRARY tcc)
find_path(TCC_INCLUDE_DIR libtcc.h)
if(TCC_LIBRARY AND TCC_INCLUDE_DIR)
  add_executable(bench_tcc_jit bench_tcc_jit.c)
  target_include_directories(bench_tcc_jit PRIVATE ${TCC_INCLUDE_DIR})
  target_link_libraries(bench_tcc_jit PRIVATE ${TCC_LIBRARY} dl Threads::Threads)
  message(STATUS "libtcc found -- building bench_tcc_jit")
else()
  message(STATUS "libtcc not found (apt install tcc libtcc-dev) -- skipping bench_tcc_jit")
endif()
