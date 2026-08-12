// messages.hpp
//
// A small set of "essential" message types for the commsys library --
// fixed-layout POD structs covering the common robotics data this
// project has used throughout (IMU, wheel encoders, 2D pose/velocity),
// formalized here as canonical types instead of being redefined
// ad-hoc in each test/bench file the way they were before this
// header existed.
//
// Each type has a static type_name() -- not required by
// MessageTraits<T> (which only needs data()/size()/deserialize()),
// but used by rosbag.hpp for connection metadata (the equivalent of
// ROS's "sensor_msgs/msg/Imu" type strings in bag file introspection)
// and generally useful anywhere a human-readable type identifier is
// worth having. Deliberately small: this is not an attempt at
// ROS's full common_msgs/sensor_msgs package set, just the handful
// of shapes this project's own benchmarks and examples actually use.
//
// Variable-length messages (LaserScan-class data) are not modeled as
// POD structs here -- use RawBytes (message_traits.hpp) with a
// FlatBuffers-built buffer instead, the same pattern the rest of this
// project already uses for that case.
#pragma once

#include <cstdint>

namespace commsys {
namespace msg {

struct Imu {
    uint64_t timestamp_ns = 0;
    float accel_x = 0, accel_y = 0, accel_z = 0;  // m/s^2
    float gyro_x = 0, gyro_y = 0, gyro_z = 0;      // rad/s
    static constexpr const char* type_name() { return "commsys/Imu"; }
};

struct Encoder {
    uint64_t timestamp_ns = 0;
    int64_t left_ticks = 0;
    int64_t right_ticks = 0;
    float velocity_mps = 0;
    static constexpr const char* type_name() { return "commsys/Encoder"; }
};

struct Pose2D {
    uint64_t timestamp_ns = 0;
    float x = 0, y = 0, theta = 0;
    static constexpr const char* type_name() { return "commsys/Pose2D"; }
};

struct Twist2D {
    uint64_t timestamp_ns = 0;
    float linear_x = 0;
    float angular_z = 0;
    static constexpr const char* type_name() { return "commsys/Twist2D"; }
};

struct BatteryState {
    uint64_t timestamp_ns = 0;
    float voltage = 0;
    float percentage = 0;  // 0.0-1.0
    static constexpr const char* type_name() { return "commsys/BatteryState"; }
};

}  // namespace msg
}  // namespace commsys
