// message_traits.hpp
//
// Typed pub/sub on top of Node's raw (const uint8_t*, uint32_t) API,
// without changing anything about that underlying API -- it's already
// tested and benchmarked, so this is a thin layer on top, not a
// rewrite.
//
// Two supported cases, matching the two real message shapes this
// project has actually used:
//
//   1. Trivially-copyable POD structs (ImuSample, EncoderSample-style
//      fixed-layout types). No specialization needed -- the default
//      MessageTraits<T> treats T's own bytes as the wire format via
//      memcpy, which is exactly what the raw struct.pack-equivalent
//      benchmarks in this project already showed is the fastest
//      option for small, high-frequency messages (see
//      cpp/CPP_PORT_REPORT.md and the earlier struct-vs-FlatBuffers
//      comparison).
//
//   2. Pre-serialized variable-length messages (FlatBuffers-built
//      buffers, the LaserScan case). Use the RawBytes wrapper type --
//      no copying, no interpretation, the bytes are the message.
//
// For anything else (e.g. a type that needs real serialization logic,
// not just memcpy), specialize MessageTraits<T> yourself:
//
//   template <> struct commsys::MessageTraits<MyType> {
//       static std::vector<uint8_t> serialize(const MyType& msg) {...}
//       static MyType deserialize(const uint8_t* data, uint32_t len) {...}
//   };
//
// Deliberately NOT trying to be a general serialization framework --
// this project's whole thesis is that hand-picking the right wire
// representation per message type (raw struct vs FlatBuffers) matters
// for performance, and a generic "serialize anything" layer would
// paper over exactly the distinction that mattered.
#pragma once

#include <cstdint>
#include <cstring>
#include <type_traits>
#include <vector>

namespace commsys {

// Wrap an already-serialized buffer (e.g. the output of
// flatbuffer_codec-equivalent build_*() functions) to publish/
// subscribe it through the typed API without any copying.
//
// Ownership note: RawBytes never owns memory. When constructed by
// the user for publish(), the caller keeps the buffer alive for the
// duration of the call. When received via subscribe<RawBytes>(), the
// view is only valid for the duration of the callback -- copy out
// (e.g. via a FlatBuffers accessor's own field reads) before
// returning if you need the data later, the same rule the raw
// (const uint8_t*, uint32_t) API already has.
struct RawBytes {
    const uint8_t* data = nullptr;
    uint32_t size = 0;

    RawBytes() = default;
    RawBytes(const uint8_t* d, uint32_t s) : data(d), size(s) {}
    explicit RawBytes(const std::vector<uint8_t>& v) : data(v.data()), size((uint32_t)v.size()) {}
};

// Primary template: works automatically for any trivially-copyable
// type (the common case -- fixed-layout structs like IMU/encoder
// samples). Anything else needs an explicit specialization; the
// static_assert gives a clear compile error pointing at why, instead
// of a wall of template-instantiation noise.
template <typename T, typename Enable = void>
struct MessageTraits {
    static_assert(std::is_trivially_copyable<T>::value,
        "commsys::MessageTraits<T>: T has no specialization and isn't "
        "trivially copyable, so there's no safe default wire "
        "representation for it. Either use a trivially-copyable POD "
        "struct (the fast path for small/high-frequency messages), use "
        "RawBytes for a pre-serialized buffer (e.g. FlatBuffers), or "
        "specialize MessageTraits<T> yourself with serialize()/"
        "deserialize().");

    static const uint8_t* data(const T& msg) {
        return reinterpret_cast<const uint8_t*>(&msg);
    }
    static uint32_t size(const T&) { return (uint32_t)sizeof(T); }

    static T deserialize(const uint8_t* data, uint32_t len) {
        T msg{};
        // A subscriber on a different build (e.g. a struct definition
        // that drifted between publisher and subscriber binaries)
        // could send a mismatched size; memcpy-ing sizeof(T) from a
        // shorter buffer would read out of bounds, so guard it rather
        // than trust the wire.
        std::memcpy(&msg, data, len < sizeof(T) ? len : sizeof(T));
        return msg;
    }
};

template <>
struct MessageTraits<RawBytes> {
    static const uint8_t* data(const RawBytes& msg) { return msg.data; }
    static uint32_t size(const RawBytes& msg) { return msg.size; }
    static RawBytes deserialize(const uint8_t* data, uint32_t len) { return RawBytes(data, len); }
};

// A (pointer, length) pair describing a message's wire representation
// -- what to_bytes() returns. Deliberately not just
// std::pair<const uint8_t*, uint32_t>: named fields read better at
// call sites (view.data / view.size, not view.first / view.second),
// and this documents its own lifetime rule right next to its use.
struct BytesView {
    const uint8_t* data = nullptr;
    uint32_t size = 0;
};

// Explicit, directly-usable, and directly unit-testable wrapper
// around MessageTraits<T> -- this is the single place both Node's
// publish<T>()/subscribe<T>() and any external caller go through to
// convert a typed message to/from its wire representation, rather
// than each call site reaching into MessageTraits<T>::data()/size()/
// deserialize() separately. Useful on its own too: anything that
// wants to inspect, log, or hand-test a message's wire bytes without
// spinning up a Node can call these directly.
//
// Lifetime: the returned BytesView borrows from `msg` (points into
// it, for a trivially-copyable T, or into whatever RawBytes/custom
// MessageTraits<T>::data() returns) -- it is only valid as long as
// `msg` is. This mirrors the existing rule for Node's raw
// (const uint8_t*, uint32_t) API and RawBytes's own doc comment.
template <typename T>
BytesView to_bytes(const T& msg) {
    return BytesView{MessageTraits<T>::data(msg), MessageTraits<T>::size(msg)};
}

template <typename T>
T from_bytes(const uint8_t* data, uint32_t len) {
    return MessageTraits<T>::deserialize(data, len);
}

template <typename T>
T from_bytes(const BytesView& view) {
    return MessageTraits<T>::deserialize(view.data, view.size);
}

}  // namespace commsys
