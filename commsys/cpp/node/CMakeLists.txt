cmake_minimum_required(VERSION 3.16)

include(GNUInstallDirs)  # needed early: CMAKE_INSTALL_INCLUDEDIR is used below

# Header-only library: discovery.hpp, ring_buffer.hpp,
# latest_value_slot.hpp, message_traits.hpp, node.hpp, ros_compat.hpp.
# INTERFACE because there's no .cpp to compile -- everything here is
# templates/inline, same as how the project has been building it by
# hand with `-I.` all along.
add_library(commsys_node INTERFACE)
add_library(commsys::node ALIAS commsys_node)
# EXPORT_NAME controls what install(EXPORT ... NAMESPACE commsys::)
# combines with the namespace for external consumers. Without this,
# CMake uses the target's own name (commsys_node), producing
# commsys::commsys_node for find_package() consumers -- functionally
# fine but inconsistent with the commsys::node spelling the ALIAS
# above gives in-tree users, and with what API_GUIDE.md documents.
# Caught by actually building a throwaway external consumer project
# against a real `cmake --install`, not assumed to work from reading
# the CMake docs.
set_target_properties(commsys_node PROPERTIES EXPORT_NAME node)

# Two different include conventions, deliberately: in-tree development
# (this repo's own bench/*.cpp and tests/*.cpp) keeps using
# `#include "include/node.hpp"` unchanged, since that's how every
# existing file here has always included it (compiled with `-I.` from
# this directory). External consumers of the installed package get a
# clean, namespaced `#include <commsys/node.hpp>` instead -- headers
# are installed into an actual `commsys/` subfolder below, not flat
# into the install prefix's include dir, specifically so a consumer's
# own `node.hpp` (if they happen to have one) can never collide.
target_include_directories(commsys_node INTERFACE
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}>
  $<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>
)
target_link_libraries(commsys_node INTERFACE rt Threads::Threads)
target_compile_features(commsys_node INTERFACE cxx_std_17)

function(commsys_add_executable name source)
  add_executable(${name} ${source})
  target_link_libraries(${name} PRIVATE commsys::node)
endfunction()

if(COMMSYS_BUILD_EXAMPLES)
  commsys_add_executable(test_node_basic bench/test_node_basic.cpp)
  commsys_add_executable(test_node_udp_latest bench/test_node_udp_latest.cpp)
  commsys_add_executable(test_ring_stress bench/test_ring_stress.cpp)
  commsys_add_executable(test_typed_api bench/test_typed_api.cpp)
  commsys_add_executable(benchmark_report bench/benchmark_report.cpp)
  commsys_add_executable(bench_cpu_affinity bench/bench_cpu_affinity.cpp)
  commsys_add_executable(commsys_bag tools/commsys_bag.cpp)
  commsys_add_executable(csv_imu_publisher tools/csv_imu_publisher.cpp)

  # A single target that runs every smoke test in sequence and fails
  # the build if any of them does -- this is what
  # build.sh/benchmark.sh actually invoke, rather than each script
  # re-listing every binary.
  add_custom_target(run_smoke_tests
    COMMAND ${CMAKE_COMMAND} -E rm -rf /dev/shm/commsys_cpp_*
    COMMAND $<TARGET_FILE:test_node_basic>
    COMMAND ${CMAKE_COMMAND} -E rm -rf /dev/shm/commsys_cpp_*
    COMMAND $<TARGET_FILE:test_node_udp_latest>
    COMMAND ${CMAKE_COMMAND} -E rm -rf /dev/shm/commsys_cpp_*
    COMMAND $<TARGET_FILE:test_ring_stress>
    COMMAND ${CMAKE_COMMAND} -E rm -rf /dev/shm/commsys_cpp_*
    COMMAND $<TARGET_FILE:test_typed_api>
    COMMAND ${CMAKE_COMMAND} -E rm -rf /dev/shm/commsys_cpp_*
    DEPENDS test_node_basic test_node_udp_latest test_ring_stress test_typed_api
    USES_TERMINAL
  )
endif()

if(COMMSYS_BUILD_TESTS)
  add_subdirectory(tests)
endif()

# --- Standalone-library install/export support -----------------------
if(COMMSYS_INSTALL)
  include(CMakePackageConfigHelpers)

  install(TARGETS commsys_node
    EXPORT commsysTargets
  )
  install(DIRECTORY ${CMAKE_CURRENT_SOURCE_DIR}/include/
    DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/commsys
    FILES_MATCHING PATTERN "*.hpp"
  )
  install(EXPORT commsysTargets
    FILE commsysTargets.cmake
    NAMESPACE commsys::
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/commsys
  )

  configure_package_config_file(
    ${CMAKE_CURRENT_SOURCE_DIR}/cmake/commsysConfig.cmake.in
    ${CMAKE_CURRENT_BINARY_DIR}/commsysConfig.cmake
    INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/commsys
  )
  write_basic_package_version_file(
    ${CMAKE_CURRENT_BINARY_DIR}/commsysConfigVersion.cmake
    VERSION ${PROJECT_VERSION}
    COMPATIBILITY SameMajorVersion
  )
  install(FILES
    ${CMAKE_CURRENT_BINARY_DIR}/commsysConfig.cmake
    ${CMAKE_CURRENT_BINARY_DIR}/commsysConfigVersion.cmake
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/commsys
  )
endif()
