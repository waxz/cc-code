cmake_minimum_required(VERSION 3.16)

# Header-only library: discovery.hpp, ring_buffer.hpp,
# latest_value_slot.hpp, node.hpp. INTERFACE because there's no .cpp
# to compile -- everything here is templates/inline, same as how the
# project has been building it by hand with `-I.` all along.
add_library(commsys_node INTERFACE)
target_include_directories(commsys_node INTERFACE ${CMAKE_CURRENT_SOURCE_DIR})
target_link_libraries(commsys_node INTERFACE rt Threads::Threads)

function(commsys_add_executable name source)
  add_executable(${name} ${source})
  target_link_libraries(${name} PRIVATE commsys_node)
endfunction()

commsys_add_executable(test_node_basic bench/test_node_basic.cpp)
commsys_add_executable(test_node_udp_latest bench/test_node_udp_latest.cpp)
commsys_add_executable(test_ring_stress bench/test_ring_stress.cpp)
commsys_add_executable(benchmark_report bench/benchmark_report.cpp)
commsys_add_executable(bench_cpu_affinity bench/bench_cpu_affinity.cpp)

# A single target that runs every smoke test in sequence and fails
# the build if any of them does -- this is what build.sh/benchmark.sh
# actually invoke, rather than each script re-listing every binary.
add_custom_target(run_smoke_tests
  COMMAND ${CMAKE_COMMAND} -E rm -rf /dev/shm/commsys_cpp_*
  COMMAND $<TARGET_FILE:test_node_basic>
  COMMAND ${CMAKE_COMMAND} -E rm -rf /dev/shm/commsys_cpp_*
  COMMAND $<TARGET_FILE:test_node_udp_latest>
  COMMAND ${CMAKE_COMMAND} -E rm -rf /dev/shm/commsys_cpp_*
  COMMAND $<TARGET_FILE:test_ring_stress>
  COMMAND ${CMAKE_COMMAND} -E rm -rf /dev/shm/commsys_cpp_*
  DEPENDS test_node_basic test_node_udp_latest test_ring_stress
  USES_TERMINAL
)
