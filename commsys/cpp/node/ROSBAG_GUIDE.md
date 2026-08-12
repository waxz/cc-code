# commsys_bag: record, play, and inspect topic sessions

A CLI mimicking `ros2 bag`'s shape (`record`/`play`/`info`), built on
`commsys::Node`'s raw publish/subscribe API and a small custom bag
format (`rosbag.hpp`). **Not compatible with real ROS1/ROS2 bag
files** -- a deliberately simpler format, not a reimplementation of
either. See `rosbag.hpp`'s header comment for the exact file layout
and why it looks the way it does (no sqlite3 dependency, no index --
sequential read is enough for the bag sizes this is meant for).

## Essential message types

`messages.hpp` defines a small set of canonical POD message types
used throughout this project's examples and tests: `msg::Imu`,
`msg::Encoder`, `msg::Pose2D`, `msg::Twist2D`, `msg::BatteryState`.
Each has a `type_name()` used for bag connection metadata (the
equivalent of ROS's `sensor_msgs/msg/Imu`-style type strings). Not an
attempt at ROS's full message package set -- just the shapes this
project's own benchmarks actually use. For anything else, publish raw
bytes (`commsys_bag record` works with any topic regardless of type,
since it records whatever bytes it sees) or a FlatBuffers-built
buffer via `RawBytes`.

## Usage

```bash
# Record two topics until Ctrl+C (or --duration N seconds)
commsys_bag record -o session.bag imu pose

# Inspect what's in it (mirrors `ros2 bag info`)
commsys_bag info session.bag

# Replay it -- topics are re-advertised and published with their
# original relative timing, honoring --rate
commsys_bag play session.bag --rate 2.0
```

All three subcommands accept `--registry NAME` (discovery domain
isolation, same as `NodeOptions::registry_name`) and `--transport
shm|udp` (same as `NodeOptions::force_transport`).

## Demo: the full pipeline against real external data

`tools/demo_rosbag_pipeline.sh` downloads a real IMU dataset
([MotionSense](https://github.com/mmalekzadeh/motion-sense),
Malekzadeh et al., IoTDI'19 -- cite the paper if you use the data
yourself) and runs it through the complete pipeline: parse the CSV ->
publish via `commsys::Node` -> `commsys_bag record` captures it ->
`commsys_bag info` inspects it -> `commsys_bag play` replays it.

```bash
./build.sh   # if not already built
./tools/demo_rosbag_pipeline.sh build
```

This was run for real during development, not just written and
assumed to work: 896 real accelerometer/gyroscope readings parsed
from the dataset's `dws_11/sub_1.csv` (a real smartphone recording),
published, recorded, and played back -- with a subscriber verifying
the replayed values matched independently-computed expected values
from the original CSV exactly (both the accelerometer reading,
computed as `userAcceleration + gravity`, and the gyroscope reading
from `rotationRate`), plus strictly-increasing timestamp ordering
across all 896 messages. See `tests/test_rosbag.cpp` for the
equivalent automated coverage (using synthetic data there, so it
doesn't depend on network access during CI).

## What's out of scope

- **Not ROS bag format compatible.** A real `.bag`/`.db3` file will
  not open with `commsys_bag`, and vice versa. If you need actual
  interoperability with ROS tooling, that would mean implementing
  ROS1's documented binary bag format (or ROS2's sqlite3 schema)
  specifically -- a real, substantial undertaking not attempted here,
  not something silently assumed to be "close enough."
- **No index or random access.** `info` does a full sequential scan;
  fine for the recording lengths this is meant for (a robotics
  session, not archival-scale data), not fine for scrubbing through a
  multi-gigabyte file.
- **Message types recorded as "unknown" by `commsys_bag record`.**
  The recorder subscribes raw (it doesn't need to know a message's
  real type to record its bytes), so `info`'s type column shows
  `unknown` for anything recorded this way. If you want accurate type
  names in `info`, use `rosbag::BagWriter` directly in your own code
  (as `test_rosbag.cpp`'s integration test does) and pass the real
  type name from `MessageTraits<T>`/`msg::T::type_name()`.
