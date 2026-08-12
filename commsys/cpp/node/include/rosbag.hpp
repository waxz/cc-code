// rosbag.hpp
//
// A small, custom bag file format for recording and replaying
// commsys topics -- conceptually similar to ROS1's classic `.bag`
// format (a sequence of connection records + timestamped message
// records in one file), not a byte-for-byte reimplementation of it
// and not compatible with ROS1/ROS2 bag files. Deliberately simple:
// no sqlite3 dependency (ROS2's default bag storage), no index/chunk
// compression, no random-access seeking -- sequential read is enough
// for record/play/info, and matches this project's general
// "don't add a dependency for something a few hundred lines of
// straightforward code covers" approach (see e.g. the reliable-UDP
// channel or the discovery registry, neither of which reach for an
// existing message-queue or service-discovery library either).
//
// File format:
//   magic:    4 bytes, "CBAG"
//   version:  uint32
//   records:  a sequence of one of two record kinds, each starting
//             with a 1-byte tag:
//
//     CONNECTION (tag=1): written once the first time a topic is
//       seen. topic_id(uint32), topic_name (uint16 length + bytes),
//       type_name (uint16 length + bytes).
//
//     MESSAGE (tag=2): topic_id(uint32), timestamp_ns(uint64),
//       payload_len(uint32), payload bytes. Recorded raw -- the bag
//       format itself doesn't need to know a message's real type to
//       store or replay it (Node's raw publish/subscribe API doesn't
//       either); type_name is carried purely for `info`-style
//       introspection, the same way ROS bag metadata is descriptive,
//       not required for the bytes themselves to round-trip.
#pragma once

#include <cstdint>
#include <cstring>
#include <fstream>
#include <functional>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace commsys {
namespace rosbag {

constexpr char MAGIC[4] = {'C', 'B', 'A', 'G'};
constexpr uint32_t FORMAT_VERSION = 1;
constexpr uint8_t RECORD_CONNECTION = 1;
constexpr uint8_t RECORD_MESSAGE = 2;

struct Connection {
    uint32_t topic_id;
    std::string topic_name;
    std::string type_name;
};

struct MessageRecord {
    uint32_t topic_id;
    uint64_t timestamp_ns;
    std::vector<uint8_t> payload;
};

class BagError : public std::runtime_error {
public:
    explicit BagError(const std::string& what) : std::runtime_error(what) {}
};

// --- low-level binary helpers -----------------------------------------
namespace detail {

inline void write_u16(std::ostream& os, uint16_t v) { os.write(reinterpret_cast<char*>(&v), 2); }
inline void write_u32(std::ostream& os, uint32_t v) { os.write(reinterpret_cast<char*>(&v), 4); }
inline void write_u64(std::ostream& os, uint64_t v) { os.write(reinterpret_cast<char*>(&v), 8); }
inline void write_str(std::ostream& os, const std::string& s) {
    write_u16(os, (uint16_t)s.size());
    os.write(s.data(), (std::streamsize)s.size());
}

inline bool read_u8(std::istream& is, uint8_t& v) { return (bool)is.read(reinterpret_cast<char*>(&v), 1); }
inline bool read_u16(std::istream& is, uint16_t& v) { return (bool)is.read(reinterpret_cast<char*>(&v), 2); }
inline bool read_u32(std::istream& is, uint32_t& v) { return (bool)is.read(reinterpret_cast<char*>(&v), 4); }
inline bool read_u64(std::istream& is, uint64_t& v) { return (bool)is.read(reinterpret_cast<char*>(&v), 8); }
inline bool read_str(std::istream& is, std::string& s) {
    uint16_t len;
    if (!read_u16(is, len)) return false;
    s.resize(len);
    if (len) return (bool)is.read(&s[0], len);
    return true;
}

}  // namespace detail

// --- writer -------------------------------------------------------------
class BagWriter {
public:
    explicit BagWriter(const std::string& path) : out_(path, std::ios::binary) {
        if (!out_) throw BagError("cannot open bag file for writing: " + path);
        out_.write(MAGIC, 4);
        detail::write_u32(out_, FORMAT_VERSION);
    }

    ~BagWriter() { close(); }
    BagWriter(const BagWriter&) = delete;
    BagWriter& operator=(const BagWriter&) = delete;

    /// Returns the topic's id, registering a new connection record the
    /// first time a given topic_name is seen. Safe to call repeatedly
    /// for the same topic (idempotent after the first call).
    uint32_t add_connection(const std::string& topic_name, const std::string& type_name) {
        auto it = topic_ids_.find(topic_name);
        if (it != topic_ids_.end()) return it->second;
        uint32_t id = next_topic_id_++;
        topic_ids_[topic_name] = id;

        out_.put((char)RECORD_CONNECTION);
        detail::write_u32(out_, id);
        detail::write_str(out_, topic_name);
        detail::write_str(out_, type_name);
        return id;
    }

    void write_message(uint32_t topic_id, uint64_t timestamp_ns, const uint8_t* payload, uint32_t len) {
        out_.put((char)RECORD_MESSAGE);
        detail::write_u32(out_, topic_id);
        detail::write_u64(out_, timestamp_ns);
        detail::write_u32(out_, len);
        if (len) out_.write(reinterpret_cast<const char*>(payload), len);
        message_count_++;
    }

    /// Convenience: registers the connection if new, then writes the
    /// message in one call -- the shape `commsys_bag record` actually
    /// uses per received message.
    void write_message(const std::string& topic_name, const std::string& type_name,
                        uint64_t timestamp_ns, const uint8_t* payload, uint32_t len) {
        uint32_t id = add_connection(topic_name, type_name);
        write_message(id, timestamp_ns, payload, len);
    }

    uint64_t message_count() const { return message_count_; }

    void close() {
        if (out_.is_open()) {
            out_.flush();
            out_.close();
        }
    }

private:
    std::ofstream out_;
    std::map<std::string, uint32_t> topic_ids_;
    uint32_t next_topic_id_ = 1;
    uint64_t message_count_ = 0;
};

// --- reader -------------------------------------------------------------
class BagReader {
public:
    explicit BagReader(const std::string& path) : in_(path, std::ios::binary) {
        if (!in_) throw BagError("cannot open bag file for reading: " + path);
        char magic[4];
        in_.read(magic, 4);
        if (!in_ || std::memcmp(magic, MAGIC, 4) != 0)
            throw BagError("not a commsys bag file (bad magic): " + path);
        uint32_t version;
        if (!detail::read_u32(in_, version) || version != FORMAT_VERSION)
            throw BagError("unsupported bag format version in: " + path);
    }

    BagReader(const BagReader&) = delete;
    BagReader& operator=(const BagReader&) = delete;

    /// Streams every record in file order, calling on_connection for
    /// each CONNECTION record and on_message for each MESSAGE record,
    /// in the order they appear in the file. Both callbacks are
    /// optional (pass nullptr to skip). Rewinds to just past the
    /// header before starting, so this can be called more than once
    /// on the same BagReader (e.g. one pass to build a topic-id ->
    /// name/type map, another to replay messages).
    void for_each_record(const std::function<void(const Connection&)>& on_connection,
                          const std::function<void(const MessageRecord&)>& on_message) {
        in_.clear();
        in_.seekg(8);  // just past the 4-byte magic + 4-byte version
        uint8_t tag;
        while (detail::read_u8(in_, tag)) {
            if (tag == RECORD_CONNECTION) {
                Connection c;
                if (!detail::read_u32(in_, c.topic_id)) throw BagError("truncated connection record");
                if (!detail::read_str(in_, c.topic_name)) throw BagError("truncated connection record");
                if (!detail::read_str(in_, c.type_name)) throw BagError("truncated connection record");
                if (on_connection) on_connection(c);
            } else if (tag == RECORD_MESSAGE) {
                MessageRecord m;
                uint32_t len;
                if (!detail::read_u32(in_, m.topic_id)) throw BagError("truncated message record");
                if (!detail::read_u64(in_, m.timestamp_ns)) throw BagError("truncated message record");
                if (!detail::read_u32(in_, len)) throw BagError("truncated message record");
                m.payload.resize(len);
                if (len && !in_.read(reinterpret_cast<char*>(m.payload.data()), len))
                    throw BagError("truncated message payload");
                if (on_message) on_message(m);
            } else {
                throw BagError("corrupt bag file: unknown record tag");
            }
        }
    }

    struct TopicSummary {
        std::string type_name;
        uint64_t count = 0;
    };

    struct Summary {
        uint64_t total_messages = 0;
        uint64_t start_ns = UINT64_MAX;
        uint64_t end_ns = 0;
        std::map<std::string, TopicSummary> by_topic;  // topic_name -> summary
    };

    /// One full sequential scan producing the aggregate stats
    /// `commsys_bag info` reports. O(file size); this format has no
    /// index, so there's no cheaper way to get exact counts -- fine
    /// for the bag sizes this tool is meant for (a few recorded
    /// robotics sessions, not archival-scale data).
    Summary summarize() {
        Summary s;
        std::map<uint32_t, std::string> id_to_name;
        for_each_record(
            [&](const Connection& c) {
                id_to_name[c.topic_id] = c.topic_name;
                s.by_topic[c.topic_name].type_name = c.type_name;
            },
            [&](const MessageRecord& m) {
                s.total_messages++;
                if (m.timestamp_ns < s.start_ns) s.start_ns = m.timestamp_ns;
                if (m.timestamp_ns > s.end_ns) s.end_ns = m.timestamp_ns;
                auto it = id_to_name.find(m.topic_id);
                std::string name = it != id_to_name.end() ? it->second : "<unknown>";
                s.by_topic[name].count++;
            });
        return s;
    }

private:
    std::ifstream in_;
};

}  // namespace rosbag
}  // namespace commsys
