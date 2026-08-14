// ros1_bag_reader.hpp
//
// A reader for the real ROS1 `.bag` file format (documented at
// http://wiki.ros.org/Bags/Format/2.0), independent of ROS itself --
// no rosbag/roscpp/rospy dependency, just the documented binary
// layout. Verified against a genuinely valid bag file, not assumed
// correct from reading the spec: generated with the independent
// `rosbags` Python library (real sensor_msgs/Imu messages, real
// serialization), and this parser's output cross-checked against
// what that same library reads back.
//
// What's supported: the CHUNK-based storage every `rosrun rosbag
// record` session produces (uncompressed or bz2-compressed -- bz2 is
// rosbag record's actual default compression, so this isn't an
// edge case skipped for convenience). What's NOT supported: lz4
// compression (rarer in practice, would need liblz4), and this
// reader does not attempt to deserialize message *bodies* into
// typed fields -- it hands back the raw ROS-serialized bytes per
// message, the same way commsys's own raw publish/subscribe API and
// rosbag.hpp's CBAG format both already work. That's deliberate, not
// a missing feature: decoding ROS's field-level wire format for an
// arbitrary message type needs that type's .msg definition (present
// in the bag's connection records as `message_definition`, but
// turning that into a general-purpose deserializer is a much larger
// undertaking than parsing the bag *container* format, and not
// needed for record/play/info, which only need to move bytes
// around correctly, not interpret them).
#pragma once

#include <bzlib.h>

#include <cstdint>
#include <cstring>
#include <fstream>
#include <functional>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace commsys {
namespace ros1bag {

struct Connection {
    uint32_t conn_id;
    std::string topic;
    std::string type;     // e.g. "sensor_msgs/Imu"
    std::string md5sum;
};

struct Message {
    uint32_t conn_id;
    uint64_t timestamp_ns;
    std::vector<uint8_t> data;  // raw ROS-serialized message bytes, opaque here
};

class Ros1BagError : public std::runtime_error {
public:
    explicit Ros1BagError(const std::string& what) : std::runtime_error(what) {}
};

namespace detail {

constexpr uint8_t OP_MSG_DATA = 0x02;
constexpr uint8_t OP_FILE_HEADER = 0x03;
constexpr uint8_t OP_INDEX_DATA = 0x04;
constexpr uint8_t OP_CHUNK = 0x05;
constexpr uint8_t OP_CHUNK_INFO = 0x06;
constexpr uint8_t OP_CONNECTION = 0x07;

inline uint32_t read_u32(const uint8_t* p) {
    uint32_t v;
    std::memcpy(&v, p, 4);
    return v;
}
inline uint64_t read_u64(const uint8_t* p) {
    uint64_t v;
    std::memcpy(&v, p, 8);
    return v;
}

// A record header is a sequence of length-prefixed "key=value" byte
// fields packed back to back until header_len bytes are consumed.
// Values aren't necessarily text (conn/time are binary integers), so
// this returns raw bytes per field, not strings -- callers interpret
// each field according to what it's supposed to hold.
inline std::map<std::string, std::vector<uint8_t>> parse_header_fields(const uint8_t* data, uint32_t len) {
    std::map<std::string, std::vector<uint8_t>> fields;
    uint32_t i = 0;
    while (i + 4 <= len) {
        uint32_t flen = read_u32(data + i);
        i += 4;
        if (i + flen > len) throw Ros1BagError("corrupt bag: header field overruns record");
        const uint8_t* field = data + i;
        // find '=' separating key from value within this field
        uint32_t eq = 0;
        while (eq < flen && field[eq] != '=') eq++;
        if (eq == flen) throw Ros1BagError("corrupt bag: header field missing '='");
        std::string key((const char*)field, eq);
        std::vector<uint8_t> value(field + eq + 1, field + flen);
        fields[key] = std::move(value);
        i += flen;
    }
    return fields;
}

inline std::string field_str(const std::map<std::string, std::vector<uint8_t>>& f, const std::string& key,
                              const std::string& def = "") {
    auto it = f.find(key);
    if (it == f.end()) return def;
    return std::string((const char*)it->second.data(), it->second.size());
}

// Decompress a bz2-compressed chunk. Throws with a clear message if
// libbz2 (linked at build time) reports failure, rather than
// returning corrupt/truncated data silently.
inline std::vector<uint8_t> bz2_decompress(const uint8_t* src, uint32_t src_len, uint32_t dst_len_hint) {
    std::vector<uint8_t> out(dst_len_hint);
    unsigned int out_len = dst_len_hint;
    int rc = BZ2_bzBuffToBuffDecompress(reinterpret_cast<char*>(out.data()), &out_len,
                                         const_cast<char*>(reinterpret_cast<const char*>(src)), src_len, 0, 0);
    if (rc != BZ_OK) throw Ros1BagError("bz2 decompression failed (code " + std::to_string(rc) + ")");
    out.resize(out_len);
    return out;
}

}  // namespace detail

class Ros1BagReader {
public:
    explicit Ros1BagReader(const std::string& path) : in_(path, std::ios::binary) {
        if (!in_) throw Ros1BagError("cannot open ROS1 bag file: " + path);
        std::string magic_line;
        std::getline(in_, magic_line);
        if (magic_line.substr(0, 8) != "#ROSBAG ")
            throw Ros1BagError("not a ROS1 bag file (bad magic line): " + path);
    }

    Ros1BagReader(const Ros1BagReader&) = delete;
    Ros1BagReader& operator=(const Ros1BagReader&) = delete;

    /// Streams every connection and message in the bag, in file
    /// order. Handles both chunked (the normal case -- every
    /// `rosbag record` session writes chunked bags) and any
    /// top-level connection/message records that appear outside a
    /// chunk (rare, but valid per the format spec). Skips index-only
    /// records (INDEX_DATA, CHUNK_INFO, and the top-level FILE_HEADER
    /// itself) since none of them carry message data -- record/play/
    /// info only need the actual connections and messages, not the
    /// random-access index.
    void for_each_record(const std::function<void(const Connection&)>& on_connection,
                          const std::function<void(const Message&)>& on_message) {
        in_.clear();
        in_.seekg(0);
        std::string magic_line;
        std::getline(in_, magic_line);

        uint32_t hlen;
        while (read_exact_u32(hlen)) {
            std::vector<uint8_t> header(hlen);
            if (!read_exact(header.data(), hlen)) throw Ros1BagError("truncated record header");
            auto fields = detail::parse_header_fields(header.data(), hlen);
            auto op_it = fields.find("op");
            if (op_it == fields.end() || op_it->second.empty())
                throw Ros1BagError("corrupt bag: record missing op field");
            uint8_t op = op_it->second[0];

            uint32_t dlen;
            if (!read_exact_u32(dlen)) throw Ros1BagError("truncated record (missing data length)");
            std::vector<uint8_t> data(dlen);
            if (dlen && !read_exact(data.data(), dlen)) throw Ros1BagError("truncated record data");

            if (op == detail::OP_CHUNK) {
                std::string compression = detail::field_str(fields, "compression");
                uint32_t uncompressed_size = fields.count("size") ? detail::read_u32(fields["size"].data()) : 0;
                std::vector<uint8_t> chunk_data;
                if (compression == "none") {
                    chunk_data = std::move(data);
                } else if (compression == "bz2") {
                    chunk_data = detail::bz2_decompress(data.data(), (uint32_t)data.size(), uncompressed_size);
                } else {
                    throw Ros1BagError("unsupported chunk compression '" + compression +
                                        "' (only 'none' and 'bz2' are supported -- lz4 is not)");
                }
                parse_records_in_buffer(chunk_data.data(), (uint32_t)chunk_data.size(), on_connection, on_message);
            } else if (op == detail::OP_CONNECTION) {
                emit_connection(fields, data, on_connection);
            } else if (op == detail::OP_MSG_DATA) {
                emit_message(fields, data, on_message);
            }
            // OP_FILE_HEADER, OP_INDEX_DATA, OP_CHUNK_INFO: no message
            // data, nothing to do with them for record/play/info.
        }
    }

private:
    bool read_exact(uint8_t* dst, uint32_t n) { return (bool)in_.read(reinterpret_cast<char*>(dst), n); }
    bool read_exact_u32(uint32_t& v) {
        uint8_t buf[4];
        if (!read_exact(buf, 4)) return false;
        v = detail::read_u32(buf);
        return true;
    }

    void parse_records_in_buffer(const uint8_t* buf, uint32_t len,
                                  const std::function<void(const Connection&)>& on_connection,
                                  const std::function<void(const Message&)>& on_message) {
        uint32_t i = 0;
        while (i + 4 <= len) {
            uint32_t hlen = detail::read_u32(buf + i);
            i += 4;
            if (i + hlen > len) throw Ros1BagError("corrupt chunk: header overruns buffer");
            auto fields = detail::parse_header_fields(buf + i, hlen);
            i += hlen;
            if (i + 4 > len) throw Ros1BagError("corrupt chunk: missing data length");
            uint32_t dlen = detail::read_u32(buf + i);
            i += 4;
            if (i + dlen > len) throw Ros1BagError("corrupt chunk: data overruns buffer");
            const uint8_t* data = buf + i;
            i += dlen;

            auto op_it = fields.find("op");
            if (op_it == fields.end() || op_it->second.empty()) continue;
            uint8_t op = op_it->second[0];
            std::vector<uint8_t> data_vec(data, data + dlen);
            if (op == detail::OP_CONNECTION) {
                emit_connection(fields, data_vec, on_connection);
            } else if (op == detail::OP_MSG_DATA) {
                emit_message(fields, data_vec, on_message);
            }
        }
    }

    void emit_connection(const std::map<std::string, std::vector<uint8_t>>& outer_fields,
                          const std::vector<uint8_t>& data,
                          const std::function<void(const Connection&)>& on_connection) {
        if (!on_connection) return;
        Connection c;
        c.conn_id = outer_fields.count("conn") ? detail::read_u32(outer_fields.at("conn").data()) : 0;
        // The connection record's DATA section is itself another
        // header-field blob (topic=, type=, md5sum=, message_definition=,
        // etc) -- the same length-prefixed field format as the record
        // header, nested one level deeper.
        auto inner = detail::parse_header_fields(data.data(), (uint32_t)data.size());
        c.topic = detail::field_str(inner, "topic");
        c.type = detail::field_str(inner, "type");
        c.md5sum = detail::field_str(inner, "md5sum");
        connections_[c.conn_id] = c;
        on_connection(c);
    }

    void emit_message(const std::map<std::string, std::vector<uint8_t>>& fields, const std::vector<uint8_t>& data,
                       const std::function<void(const Message&)>& on_message) {
        if (!on_message) return;
        Message m;
        m.conn_id = fields.count("conn") ? detail::read_u32(fields.at("conn").data()) : 0;
        if (fields.count("time")) {
            // ROS time on the wire: uint32 sec, uint32 nsec, packed
            // into the same 8-byte field.
            const uint8_t* t = fields.at("time").data();
            uint32_t sec = detail::read_u32(t);
            uint32_t nsec = detail::read_u32(t + 4);
            m.timestamp_ns = (uint64_t)sec * 1000000000ull + nsec;
        } else {
            m.timestamp_ns = 0;
        }
        m.data = data;
        on_message(m);
    }

    std::ifstream in_;
    std::map<uint32_t, Connection> connections_;
};

}  // namespace ros1bag
}  // namespace commsys
