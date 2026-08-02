# Node API guide

Quick reference for using `commsys::Node` in new code. See
`node.hpp`'s inline doc comments for the authoritative per-method
reference; this is the "how do I actually use this" version.

## Construction

```cpp
#include "node.hpp"
using namespace commsys;

// Minimal: everything else defaults sensibly.
Node node("my_node_id");

// Override only what matters for your use case:
Node lidar_node("lidar", {.force_transport = "shm",
                           .shm_ring_capacity = 32 << 20});
```

`node_id` must be unique across every node sharing the same discovery
domain (default: a single shared-memory table any node on the same
host can attach to; override `NodeOptions::registry_name` for test
isolation or a deliberately separate domain).

A legacy positional constructor (`Node(id, host, port, transport, ...)`)
still works for existing code, but `NodeOptions` is easier to get right
at the call site -- it's much harder to accidentally pass an argument
in the wrong position.

## Typed messages

Two supported message shapes, matching the two this project actually
uses and benchmarked:

**Small, fixed-layout POD structs** (IMU/encoder-sample style) work
automatically, zero-copy, no registration needed:

```cpp
struct ImuSample {
    uint64_t timestamp_ns;
    float ax, ay, az;
    float gx, gy, gz;
};

node.advertise("imu");
node.publish("imu", imu_sample);              // deduces ImuSample

node.subscribe<ImuSample>("imu", [](const ImuSample& msg) {
    // msg is a plain, complete copy -- keep it as long as you like
});
```

**Pre-serialized variable-length buffers** (e.g. a FlatBuffers-built
`LaserScan`) use `RawBytes` -- no copying, no reinterpretation:

```cpp
auto buf = build_laser_scan(...);  // however you already build it
node.publish("scan", RawBytes(buf.data(), (uint32_t)buf.size()));

node.subscribe<RawBytes>("scan", [](const RawBytes& raw) {
    auto* scan = flatbuffers::GetRoot<LaserScan>(raw.data);
    // raw.data is only valid for the duration of this callback --
    // copy out anything you need to keep past it, same rule as the
    // raw (const uint8_t*, uint32_t) API this wraps.
});
```

**Anything else** (a type that needs real serialization logic, not
just `memcpy`): specialize `MessageTraits<T>` yourself. See
`message_traits.hpp` for the exact interface. Deliberately not a
general-purpose serialization framework -- this project's whole point
is that the right wire format differs by message type (raw struct vs
FlatBuffers), and a generic "serialize anything" layer would erase
that distinction.

The raw `(const uint8_t*, uint32_t)` API is still there underneath and
directly usable if you'd rather manage serialization yourself.

## Driving the event loop

There's no background thread. You call `spin_once()` yourself:

```cpp
node.start();
node.advertise("topic");
node.spin_for(std::chrono::milliseconds(800));  // let discovery settle

while (running) {
    node.publish("topic", some_message);
    node.spin_once();
}
```

**The one footgun worth knowing about, because it was a real, measured
bug**: `spin_once()` is what sends this node's own heartbeat. A tight
publish loop that only calls `publish()` in a loop and never calls
`spin_once()` will silently let its own heartbeat go stale -- other
nodes will conclude it died and tear down their links to it, mid-run,
even though it's still actively publishing (see `CPP_PORT_REPORT.md`
for the full ~300ms-latency-outlier investigation this came from). Two
ways to avoid it:

```cpp
// Explicit: call spin_once() periodically yourself
int i = 0;
while (publishing) {
    node.publish("topic", msg);
    if (++i % 256 == 0) node.spin_once(0);
}

// Or: let the library do it for you
node.publish_loop_for(std::chrono::seconds(2), [&]() {
    node.publish("topic", msg);
});
```

## Error handling

Library-thrown errors use `commsys::NodeError` (a `std::runtime_error`
subclass), so you can catch commsys-specific failures without also
catching unrelated standard-library exceptions:

```cpp
try {
    node.publish("never_advertised", msg);
} catch (const NodeError& e) {
    // e.g. "publish() to un-advertised topic ..."
}
```

## Move semantics

`Node` is move-only (not copyable -- it owns OS handles and a
discovery registration that can't be safely duplicated). Safe to
store in a `std::vector<Node>`, return by value from a factory
function, etc.
