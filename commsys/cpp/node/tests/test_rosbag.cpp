#include <catch2/catch_all.hpp>
#include "../include/rosbag.hpp"
#include "../include/node.hpp"
#include "../include/messages.hpp"
#include "test_helpers.hpp"
#include <unistd.h>
#include <sys/wait.h>
#include <cstdio>
#include <chrono>

using namespace commsys;
using commsys_test::ChildProcess;

namespace {
std::string unique_bag_path() {
    return "/tmp/" + commsys_test::unique_name("test_bag").substr(1) + ".bag";
}
std::string unique_registry() { return commsys_test::unique_name("rosbag_test_disc"); }
}  // namespace

TEST_CASE("rosbag: BagWriter/BagReader round-trip connections and messages exactly", "[rosbag]") {
    auto path = unique_bag_path();
    {
        rosbag::BagWriter w(path);
        uint32_t imu_id = w.add_connection("imu", "commsys/Imu");
        uint32_t pose_id = w.add_connection("pose", "commsys/Pose2D");
        // re-adding an existing topic must return the same id, not a new one
        REQUIRE(w.add_connection("imu", "commsys/Imu") == imu_id);

        const char* p1 = "payload-1";
        w.write_message(imu_id, 1000, (const uint8_t*)p1, 9);
        const char* p2 = "payload-two";
        w.write_message(pose_id, 2000, (const uint8_t*)p2, 11);
        const char* p3 = "payload-3";
        w.write_message(imu_id, 3000, (const uint8_t*)p3, 9);
        REQUIRE(w.message_count() == 3);
    }

    rosbag::BagReader r(path);
    std::vector<rosbag::Connection> connections;
    std::vector<rosbag::MessageRecord> messages;
    r.for_each_record(
        [&](const rosbag::Connection& c) { connections.push_back(c); },
        [&](const rosbag::MessageRecord& m) { messages.push_back(m); });

    REQUIRE(connections.size() == 2);
    REQUIRE(connections[0].topic_name == "imu");
    REQUIRE(connections[0].type_name == "commsys/Imu");
    REQUIRE(connections[1].topic_name == "pose");
    REQUIRE(connections[1].type_name == "commsys/Pose2D");

    REQUIRE(messages.size() == 3);
    REQUIRE(messages[0].topic_id == connections[0].topic_id);
    REQUIRE(messages[0].timestamp_ns == 1000);
    REQUIRE(std::string((char*)messages[0].payload.data(), messages[0].payload.size()) == "payload-1");
    REQUIRE(messages[1].topic_id == connections[1].topic_id);
    REQUIRE(messages[1].timestamp_ns == 2000);
    REQUIRE(messages[2].timestamp_ns == 3000);

    std::remove(path.c_str());
}

TEST_CASE("rosbag: for_each_record can be called more than once on the same reader", "[rosbag]") {
    auto path = unique_bag_path();
    {
        rosbag::BagWriter w(path);
        uint32_t id = w.add_connection("t", "T");
        w.write_message(id, 1, (const uint8_t*)"x", 1);
    }
    rosbag::BagReader r(path);
    int pass1_count = 0, pass2_count = 0;
    r.for_each_record(nullptr, [&](const rosbag::MessageRecord&) { pass1_count++; });
    r.for_each_record(nullptr, [&](const rosbag::MessageRecord&) { pass2_count++; });
    REQUIRE(pass1_count == 1);
    REQUIRE(pass2_count == 1);
    std::remove(path.c_str());
}

TEST_CASE("rosbag: summarize() computes correct per-topic counts and duration", "[rosbag]") {
    auto path = unique_bag_path();
    {
        rosbag::BagWriter w(path);
        uint32_t imu_id = w.add_connection("imu", "commsys/Imu");
        uint32_t pose_id = w.add_connection("pose", "commsys/Pose2D");
        for (int i = 0; i < 5; i++) w.write_message(imu_id, 1000 + i * 100, (const uint8_t*)"x", 1);
        for (int i = 0; i < 3; i++) w.write_message(pose_id, 1000 + i * 100, (const uint8_t*)"y", 1);
    }
    rosbag::BagReader r(path);
    auto s = r.summarize();
    REQUIRE(s.total_messages == 8);
    REQUIRE(s.by_topic.at("imu").count == 5);
    REQUIRE(s.by_topic.at("imu").type_name == "commsys/Imu");
    REQUIRE(s.by_topic.at("pose").count == 3);
    REQUIRE(s.start_ns == 1000);
    REQUIRE(s.end_ns == 1400);
    std::remove(path.c_str());
}

TEST_CASE("rosbag: opening a non-bag file throws BagError", "[rosbag]") {
    auto path = unique_bag_path();
    {
        std::ofstream f(path, std::ios::binary);
        f << "not a bag file at all";
    }
    REQUIRE_THROWS_AS(rosbag::BagReader(path), rosbag::BagError);
    std::remove(path.c_str());
}

TEST_CASE("rosbag: opening a missing file throws BagError", "[rosbag]") {
    REQUIRE_THROWS_AS(rosbag::BagReader("/tmp/definitely_does_not_exist_12345.bag"), rosbag::BagError);
}

TEST_CASE("rosbag: record from a live publisher, then verify via BagReader", "[rosbag][fork][node]") {
    auto reg = unique_registry();
    auto path = unique_bag_path();

    pid_t pid = fork();
    REQUIRE(pid >= 0);
    if (pid == 0) {
        Node pub("bag_record_pub", {.force_transport = "shm", .registry_name = reg});
        pub.start();
        pub.advertise("imu");
        pub.spin_for(std::chrono::milliseconds(1200));
        for (int i = 0; i < 10; i++) {
            pub.publish("imu", msg::Imu{(uint64_t)i, (float)i, 0, 9.81f, 0, 0, 0});
            pub.spin_for(std::chrono::milliseconds(30));
        }
        pub.spin_for(std::chrono::milliseconds(500));
        pub.stop();
        _exit(0);
    }
    ChildProcess child(pid);

    rosbag::BagWriter writer(path);
    Node sub("bag_record_sub", {.force_transport = "shm", .registry_name = reg});
    sub.start();
    sub.subscribe("imu", [&](const uint8_t* data, uint32_t len) {
        writer.write_message("imu", msg::Imu::type_name(), 0, data, len);
    });
    sub.spin_for(std::chrono::seconds(3));
    sub.stop();
    writer.close();

    REQUIRE(child.wait() == 0);
    REQUIRE(writer.message_count() == 10);

    rosbag::BagReader reader(path);
    auto s = reader.summarize();
    REQUIRE(s.total_messages == 10);
    REQUIRE(s.by_topic.at("imu").type_name == std::string(msg::Imu::type_name()));

    std::remove(path.c_str());
}

TEST_CASE("rosbag: play a bag back through Node and verify a subscriber receives correct content", "[rosbag][fork][node]") {
    auto reg = unique_registry();
    auto path = unique_bag_path();

    // Write a bag directly (no live recording needed for this test --
    // isolates playback correctness from recording correctness, which
    // the previous test already covers).
    {
        rosbag::BagWriter w(path);
        for (int i = 0; i < 8; i++) {
            msg::Imu sample{(uint64_t)i, (float)i * 0.5f, 0, 9.81f, 0, 0, 0};
            BytesView view = to_bytes(sample);
            w.write_message("imu", msg::Imu::type_name(), (uint64_t)i * 1000000, view.data, view.size);
        }
    }

    pid_t pid = fork();
    REQUIRE(pid >= 0);
    if (pid == 0) {
        Node sub("bag_play_sub", {.force_transport = "shm", .registry_name = reg});
        sub.start();
        std::vector<msg::Imu> received;
        sub.subscribe<msg::Imu>("imu", [&](const msg::Imu& m) { received.push_back(m); });
        sub.spin_for(std::chrono::seconds(4));
        sub.stop();
        if (received.size() != 8) _exit(1);
        for (int i = 0; i < 8; i++) {
            if (received[i].timestamp_ns != (uint64_t)i) _exit(2);
            if (received[i].accel_x != (float)i * 0.5f) _exit(3);
        }
        _exit(0);
    }
    ChildProcess child(pid);

    // Replay logic mirrors commsys_bag.cpp's cmd_play, kept minimal
    // here to isolate what's being tested: does a bag written by
    // BagWriter, then read and replayed through Node's raw publish,
    // arrive correctly at a real subscriber.
    rosbag::BagReader reader(path);
    std::map<uint32_t, std::string> id_to_topic;
    std::vector<rosbag::MessageRecord> messages;
    reader.for_each_record(
        [&](const rosbag::Connection& c) { id_to_topic[c.topic_id] = c.topic_name; },
        [&](const rosbag::MessageRecord& m) { messages.push_back(m); });

    Node pub("bag_play_pub", {.force_transport = "shm", .registry_name = reg});
    pub.start();
    for (auto& [id, name] : id_to_topic) pub.advertise(name);
    pub.spin_for(std::chrono::milliseconds(1200));
    for (auto& m : messages) {
        pub.publish(id_to_topic[m.topic_id], m.payload.data(), (uint32_t)m.payload.size());
        pub.spin_for(std::chrono::milliseconds(30));
    }
    pub.spin_for(std::chrono::milliseconds(500));
    pub.stop();

    REQUIRE(child.wait() == 0);
    std::remove(path.c_str());
}
