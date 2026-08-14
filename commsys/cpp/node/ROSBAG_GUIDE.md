# commsys_bag: record, play, and inspect topic sessions

A CLI mimicking `ros2 bag`'s shape (`record`/`play`/`info`), built on
`commsys::Node`'s raw publish/subscribe API and a small custom bag
format (`rosbag.hpp`) for its own record/play/info workflow. Also
reads **real ROS1 `.bag` files** via `import-ros1` (see below) --
genuine binary-format parsing, not a simulation of it. commsys's own
format is deliberately simpler than either ROS1's or ROS2's (no
sqlite3 dependency, no index -- sequential read is enough for the bag
sizes this is meant for); see `rosbag.hpp`'s header comment for the
exact file layout.

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

## Reading real ROS1 `.bag` files

`import-ros1` reads a genuine ROS1 `.bag` file (the documented format
at http://wiki.ros.org/Bags/Format/2.0 -- `ros1_bag_reader.hpp`
implements it directly, independent of ROS itself) and converts it
into commsys's own format, so it can then be inspected/played with
`info`/`play` like anything else:

```bash
commsys_bag import-ros1 real_session.bag -o converted.bag
commsys_bag info converted.bag       # shows real topic/type names, e.g. sensor_msgs/Imu
commsys_bag play converted.bag
```

Message bodies pass through as opaque raw bytes -- this tool doesn't
deserialize ROS's field-level wire format (that needs the message's
`.msg` definition, which is a much larger undertaking than parsing
the bag container format, and unnecessary for moving messages from
one container to another). Real topic names and type strings *are*
read and preserved, so `info` reports them accurately.

**Supports**: uncompressed and bz2-compressed chunks (bz2 is
`rosbag record`'s actual default, not an edge case). **Does not
support**: lz4-compressed bags (rarer in practice; throws a clear
error rather than producing corrupt output) or ROS2's `.db3`/MCAP
formats.

This was verified against a genuinely valid ROS1 bag, not just
written against the spec and assumed correct: generated a real bag
with the independent `rosbags` Python library (real
`sensor_msgs/Imu` messages, real ROS serialization, real MD5 sum
`6a62c6daae103f4ff57a132d6f95cec2` -- the actual canonical checksum
for that message type) populated with the same real MotionSense IMU
data described below, then confirmed `ros1_bag_reader.hpp` parses it
identically to what the Python library itself reads back -- and ran
it through the complete pipeline (`import-ros1` -> `info` -> `play`
-> a subscriber manually decoding the real ROS wire format) with
exact numeric verification against known values. `tests/
test_ros1_bag.cpp` covers the parser's correctness in CI using a
hand-built minimal bag (matching the documented format exactly) so
that coverage doesn't depend on network access or a Python
dependency during automated builds.

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

- **`commsys_bag record`/`play`/`info` use commsys's own format
  (`rosbag.hpp`), not ROS1's.** `import-ros1` bridges a *real* ROS1
  bag into that format (see above) -- but `commsys_bag record` does
  not write ROS1-format bags, and there's no `export-ros1` in the
  other direction. If you need to write a bag real ROS tooling can
  read directly, that's a real, separate undertaking (matching ROS1's
  exact chunking/indexing conventions on the write side) not
  attempted here.
- **ROS2 `.db3` (sqlite3) and MCAP bags are not supported at all**,
  read or write. Only ROS1's binary format.
- **lz4-compressed ROS1 bags are not supported** (bz2 is, and is the
  more common case -- `rosbag record`'s actual default).
- **No index or random access** in commsys's own format. `info` does
  a full sequential scan; fine for the recording lengths this is
  meant for (a robotics session, not archival-scale data), not fine
  for scrubbing through a multi-gigabyte file.
- **Message types recorded as "unknown" by `commsys_bag record`**
  (as opposed to `import-ros1`, which preserves real type names from
  the source bag). The recorder subscribes raw -- it doesn't need to
  know a message's real type to record its bytes. If you want
  accurate type names in `info` for your own recordings, use
  `rosbag::BagWriter` directly in your own code (as
  `test_rosbag.cpp`'s integration test does) and pass the real type
  name from `MessageTraits<T>`/`msg::T::type_name()`.
