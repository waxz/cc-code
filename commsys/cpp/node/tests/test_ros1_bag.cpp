#include <catch2/catch_all.hpp>
#include "../include/ros1_bag_reader.hpp"
#include "test_helpers.hpp"
#include <fstream>
#include <cstring>

using namespace commsys;

namespace {

std::string unique_bag_path() { return "/tmp/" + commsys_test::unique_name("test_ros1").substr(1) + ".bag"; }

void write_u32(std::ostream& os, uint32_t v) { os.write((char*)&v, 4); }
void write_field(std::ostream& os, const std::string& key, const std::vector<uint8_t>& value) {
    std::string field = key + "=";
    std::vector<uint8_t> full(field.begin(), field.end());
    full.insert(full.end(), value.begin(), value.end());
    write_u32(os, (uint32_t)full.size());
    os.write((char*)full.data(), (std::streamsize)full.size());
}
void write_field_str(std::ostream& os, const std::string& key, const std::string& value) {
    write_field(os, key, std::vector<uint8_t>(value.begin(), value.end()));
}
std::vector<uint8_t> u32_bytes(uint32_t v) {
    std::vector<uint8_t> b(4);
    std::memcpy(b.data(), &v, 4);
    return b;
}

// Hand-builds a minimal, spec-valid, UNCOMPRESSED ROS1 bag with one
// connection and N trivial messages, all inside a single chunk --
// matching the exact record layout ros1_bag_reader.hpp documents and
// was verified against a real `rosbags`-library-generated bag. This
// exists so the test suite doesn't depend on network access or a
// Python dependency during CI; the real-data verification (a real
// sensor_msgs/Imu bag, decoded and cross-checked against known
// values) was done directly during development -- see
// ROSBAG_GUIDE.md.
std::string build_minimal_ros1_bag(const std::string& path, const std::string& topic, const std::string& type,
                                    int n_messages) {
    // Build the chunk's inner content first (connection + N messages).
    std::ostringstream chunk_inner(std::ios::binary);

    // CONNECTION record (op=7)
    {
        std::ostringstream header(std::ios::binary);
        write_field_str(header, "op", std::string(1, (char)0x07));
        write_field(header, "conn", u32_bytes(0));
        write_field_str(header, "topic", topic);
        std::string h = header.str();
        write_u32(chunk_inner, (uint32_t)h.size());
        chunk_inner.write(h.data(), (std::streamsize)h.size());

        std::ostringstream data(std::ios::binary);
        write_field_str(data, "topic", topic);
        write_field_str(data, "type", type);
        write_field_str(data, "md5sum", "deadbeefdeadbeefdeadbeefdeadbeef");
        std::string d = data.str();
        write_u32(chunk_inner, (uint32_t)d.size());
        chunk_inner.write(d.data(), (std::streamsize)d.size());
    }

    // MSG_DATA records (op=2), one per message, trivial payload "msg-N"
    for (int i = 0; i < n_messages; i++) {
        std::ostringstream header(std::ios::binary);
        write_field_str(header, "op", std::string(1, (char)0x02));
        write_field(header, "conn", u32_bytes(0));
        std::vector<uint8_t> time_bytes(8);
        uint32_t sec = i, nsec = 0;
        std::memcpy(time_bytes.data(), &sec, 4);
        std::memcpy(time_bytes.data() + 4, &nsec, 4);
        write_field(header, "time", time_bytes);
        std::string h = header.str();
        write_u32(chunk_inner, (uint32_t)h.size());
        chunk_inner.write(h.data(), (std::streamsize)h.size());

        std::string payload = "msg-" + std::to_string(i);
        write_u32(chunk_inner, (uint32_t)payload.size());
        chunk_inner.write(payload.data(), (std::streamsize)payload.size());
    }

    std::string inner = chunk_inner.str();

    // Now the file itself: magic, BAG_HEADER (op=3, minimal/unused
    // fields since this test doesn't exercise the index), then one
    // CHUNK record wrapping `inner`.
    std::ofstream f(path, std::ios::binary);
    f << "#ROSBAG V2.0\n";

    {
        std::ostringstream header(std::ios::binary);
        write_field_str(header, "op", std::string(1, (char)0x03));
        write_field(header, "index_pos", u32_bytes(0));  // unused by this reader
        write_field(header, "conn_count", u32_bytes(1));
        write_field(header, "chunk_count", u32_bytes(1));
        std::string h = header.str();
        write_u32(f, (uint32_t)h.size());
        f.write(h.data(), (std::streamsize)h.size());
        // BAG_HEADER's data is padding to a fixed size in real bags;
        // zero-length is spec-valid too (data_len is whatever it is).
        write_u32(f, 0);
    }
    {
        std::ostringstream header(std::ios::binary);
        write_field_str(header, "op", std::string(1, (char)0x05));
        write_field_str(header, "compression", "none");
        write_field(header, "size", u32_bytes((uint32_t)inner.size()));
        std::string h = header.str();
        write_u32(f, (uint32_t)h.size());
        f.write(h.data(), (std::streamsize)h.size());
        write_u32(f, (uint32_t)inner.size());
        f.write(inner.data(), (std::streamsize)inner.size());
    }
    f.close();
    return path;
}

}  // namespace

TEST_CASE("ros1bag: parses a hand-built minimal valid ROS1 bag correctly", "[ros1bag]") {
    auto path = unique_bag_path();
    build_minimal_ros1_bag(path, "/test_topic", "std_msgs/String", 5);

    ros1bag::Ros1BagReader reader(path);
    std::vector<ros1bag::Connection> connections;
    std::vector<ros1bag::Message> messages;
    reader.for_each_record(
        [&](const ros1bag::Connection& c) { connections.push_back(c); },
        [&](const ros1bag::Message& m) { messages.push_back(m); });

    REQUIRE(connections.size() == 1);
    REQUIRE(connections[0].topic == "/test_topic");
    REQUIRE(connections[0].type == "std_msgs/String");
    REQUIRE(connections[0].md5sum == "deadbeefdeadbeefdeadbeefdeadbeef");

    REQUIRE(messages.size() == 5);
    for (int i = 0; i < 5; i++) {
        REQUIRE(messages[i].conn_id == 0);
        REQUIRE(messages[i].timestamp_ns == (uint64_t)i * 1000000000ull);
        std::string payload((char*)messages[i].data.data(), messages[i].data.size());
        REQUIRE(payload == "msg-" + std::to_string(i));
    }
    std::remove(path.c_str());
}

TEST_CASE("ros1bag: opening a non-ROS1-bag file throws Ros1BagError", "[ros1bag]") {
    auto path = unique_bag_path();
    {
        std::ofstream f(path, std::ios::binary);
        f << "not a ros1 bag";
    }
    REQUIRE_THROWS_AS(ros1bag::Ros1BagReader(path), ros1bag::Ros1BagError);
    std::remove(path.c_str());
}

TEST_CASE("ros1bag: opening a missing file throws Ros1BagError", "[ros1bag]") {
    REQUIRE_THROWS_AS(ros1bag::Ros1BagReader("/tmp/definitely_missing_ros1_98765.bag"), ros1bag::Ros1BagError);
}

TEST_CASE("ros1bag: unsupported compression (lz4) throws a clear error, not silent corruption", "[ros1bag]") {
    auto path = unique_bag_path();
    {
        std::ofstream f(path, std::ios::binary);
        f << "#ROSBAG V2.0\n";
        // BAG_HEADER
        {
            std::ostringstream header(std::ios::binary);
            write_field_str(header, "op", std::string(1, (char)0x03));
            write_field(header, "index_pos", u32_bytes(0));
            write_field(header, "conn_count", u32_bytes(0));
            write_field(header, "chunk_count", u32_bytes(1));
            std::string h = header.str();
            write_u32(f, (uint32_t)h.size());
            f.write(h.data(), (std::streamsize)h.size());
            write_u32(f, 0);
        }
        // CHUNK claiming lz4 compression
        {
            std::ostringstream header(std::ios::binary);
            write_field_str(header, "op", std::string(1, (char)0x05));
            write_field_str(header, "compression", "lz4");
            write_field(header, "size", u32_bytes(100));
            std::string h = header.str();
            write_u32(f, (uint32_t)h.size());
            f.write(h.data(), (std::streamsize)h.size());
            std::string fake_data(10, 'x');
            write_u32(f, (uint32_t)fake_data.size());
            f.write(fake_data.data(), (std::streamsize)fake_data.size());
        }
    }
    ros1bag::Ros1BagReader reader(path);
    REQUIRE_THROWS_AS(reader.for_each_record(nullptr, nullptr), ros1bag::Ros1BagError);
    std::remove(path.c_str());
}

TEST_CASE("ros1bag: for_each_record can be called with null callbacks to skip a category", "[ros1bag]") {
    auto path = unique_bag_path();
    build_minimal_ros1_bag(path, "/t", "std_msgs/String", 3);
    ros1bag::Ros1BagReader reader(path);
    int msg_count = 0;
    reader.for_each_record(nullptr, [&](const ros1bag::Message&) { msg_count++; });
    REQUIRE(msg_count == 3);
    std::remove(path.c_str());
}
