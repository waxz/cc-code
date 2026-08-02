cmake_minimum_required(VERSION 3.16)
project(commsys_cpp CXX C)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if(NOT CMAKE_BUILD_TYPE)
  set(CMAKE_BUILD_TYPE Release)
endif()
set(CMAKE_CXX_FLAGS_RELEASE "-O2")

# Every target in this project links against librt (POSIX shared
# memory: shm_open/shm_unlink) and pthreads.
find_package(Threads REQUIRED)

option(COMMSYS_BUILD_REFERENCE_BENCHMARKS
       "Build the standalone microbenchmarks used to decide whether the C++ port was worth it in the first place"
       ON)

add_subdirectory(node)

if(COMMSYS_BUILD_REFERENCE_BENCHMARKS)
  add_subdirectory(bench_reference)
endif()
