cmake_minimum_required(VERSION 3.16)

# Optional, same pattern as flatbuffers/libtcc in bench_reference:
# don't fail the whole build over a missing test framework, just skip
# building tests and say why.
find_package(Catch2 3 QUIET)

if(NOT Catch2_FOUND)
  message(STATUS "Catch2 not found (apt install catch2) -- skipping unit tests")
  return()
endif()

message(STATUS "Catch2 found -- building unit tests")

add_executable(commsys_tests
  test_message_traits.cpp
  test_ring_buffer.cpp
  test_latest_value_slot.cpp
  test_discovery.cpp
  test_node.cpp
  test_ros_compat.cpp
)
target_link_libraries(commsys_tests PRIVATE commsys_node Catch2::Catch2WithMain)

include(CTest)
include(Catch)
# catch_discover_tests runs the binary at build time to enumerate
# individual TEST_CASEs into separate ctest entries. That's the usual
# recommended approach, but every TEST_CASE here does real shared-
# memory/fork() work, and running the discovery probe as part of
# *configuring* the build is more fragile in a CI container than just
# registering the whole binary as one ctest entry and letting Catch2's
# own reporter (which already gives per-SECTION detail) show what
# failed.
add_test(NAME commsys_tests COMMAND commsys_tests)
