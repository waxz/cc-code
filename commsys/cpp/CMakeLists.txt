cmake_minimum_required(VERSION 3.16)
project(commsys VERSION 1.0.0 LANGUAGES CXX C)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()
set(CMAKE_CXX_FLAGS_RELEASE "-O2")

# Every target in this project links against librt (POSIX shared
# memory: shm_open/shm_unlink) and pthreads.
find_package(Threads REQUIRED)

# Consumers of this as a standalone library (find_package(commsys),
# add_subdirectory() from a parent project) generally want just the
# header-only commsys::node target, not this repo's own dev tooling.
# Building this project directly (the common case in this repo's own
# CI/scripts) still builds everything by default.
option(COMMSYS_BUILD_REFERENCE_BENCHMARKS
       "Build the standalone microbenchmarks used to decide whether the C++ port was worth it in the first place"
       ON)
option(COMMSYS_BUILD_TESTS "Build the Catch2 unit test suite" ON)
option(COMMSYS_BUILD_EXAMPLES "Build the bench/*.cpp example and smoke-test executables" ON)
option(COMMSYS_INSTALL "Generate install rules (headers + CMake package config) for use as a standalone library" ON)

enable_testing()
add_subdirectory(node)

if(COMMSYS_BUILD_REFERENCE_BENCHMARKS)
  add_subdirectory(bench_reference)
endif()
