#include <catch2/catch_all.hpp>
#include "../include/message_traits.hpp"
#include <cstring>

using namespace commsys;

namespace {

struct ImuSample {
    uint64_t timestamp_ns;
    float ax, ay, az;
    float gx, gy, gz;

    bool operator==(const ImuSample& o) const {
        return timestamp_ns == o.timestamp_ns && ax == o.ax && ay == o.ay && az == o.az &&
               gx == o.gx && gy == o.gy && gz == o.gz;
    }
};

}  // namespace

TEST_CASE("to_bytes/from_bytes round-trip a trivially-copyable POD struct", "[message_traits]") {
    ImuSample original{42, 1.5f, -2.5f, 9.81f, 0.1f, -0.2f, 0.3f};

    BytesView view = to_bytes(original);
    REQUIRE(view.data != nullptr);
    REQUIRE(view.size == sizeof(ImuSample));

    ImuSample restored = from_bytes<ImuSample>(view.data, view.size);
    REQUIRE(restored == original);

    // the BytesView overload should give the same result
    ImuSample restored2 = from_bytes<ImuSample>(view);
    REQUIRE(restored2 == original);
}

TEST_CASE("to_bytes gives a genuine zero-copy view into the original object", "[message_traits]") {
    ImuSample original{1, 2, 3, 4, 5, 6, 7};
    BytesView view = to_bytes(original);
    // The whole point of the POD fast path: no allocation, no copy --
    // the view must point directly at the original object's memory.
    REQUIRE(view.data == reinterpret_cast<const uint8_t*>(&original));
}

TEST_CASE("deserialize is defensive against a mismatched (shorter) buffer size", "[message_traits]") {
    // Simulates a publisher/subscriber built from drifted struct
    // definitions -- deserialize() must not read past the given
    // length even if it's shorter than sizeof(T).
    ImuSample original{99, 1, 2, 3, 4, 5, 6};
    uint32_t short_len = sizeof(ImuSample) / 2;

    ImuSample restored = from_bytes<ImuSample>(reinterpret_cast<const uint8_t*>(&original), short_len);
    // Only the first half should have been copied; the rest is
    // whatever the zero-initializer left (T{} in MessageTraits).
    uint8_t expected[sizeof(ImuSample)] = {};
    std::memcpy(expected, &original, short_len);
    REQUIRE(std::memcmp(&restored, expected, sizeof(ImuSample)) == 0);
}

TEST_CASE("RawBytes wraps an existing buffer without copying", "[message_traits][rawbytes]") {
    std::vector<uint8_t> buf = {0x01, 0x02, 0x03, 0x04, 0x05};

    RawBytes rb(buf.data(), (uint32_t)buf.size());
    REQUIRE(rb.data == buf.data());
    REQUIRE(rb.size == buf.size());

    BytesView view = to_bytes(rb);
    REQUIRE(view.data == buf.data());
    REQUIRE(view.size == buf.size());

    RawBytes restored = from_bytes<RawBytes>(view.data, view.size);
    REQUIRE(restored.data == buf.data());
    REQUIRE(restored.size == buf.size());
}

TEST_CASE("RawBytes constructed from a std::vector references that vector's storage", "[message_traits][rawbytes]") {
    std::vector<uint8_t> buf = {10, 20, 30};
    RawBytes rb(buf);
    REQUIRE(rb.data == buf.data());
    REQUIRE(rb.size == 3);
}

TEST_CASE("to_bytes/from_bytes work correctly for a batch of several samples", "[message_traits]") {
    // Not a single struct, but the pattern this project actually uses
    // for IMU batching -- confirms the wrapper functions compose
    // cleanly with a caller doing its own framing on top.
    std::vector<ImuSample> samples;
    for (int i = 0; i < 10; i++) {
        samples.push_back(ImuSample{(uint64_t)i, (float)i, 0, 9.81f, 0, 0, 0});
    }
    for (auto& s : samples) {
        BytesView view = to_bytes(s);
        ImuSample restored = from_bytes<ImuSample>(view);
        REQUIRE(restored == s);
    }
}

TEST_CASE("empty RawBytes round-trips correctly", "[message_traits][rawbytes]") {
    RawBytes empty(nullptr, 0);
    BytesView view = to_bytes(empty);
    REQUIRE(view.size == 0);
}
