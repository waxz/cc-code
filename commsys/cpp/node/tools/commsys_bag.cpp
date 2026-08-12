// commsys_bag.cpp
//
// A CLI mimicking `ros2 bag`'s shape (record/play/info subcommands),
// built on commsys::Node's raw publish/subscribe API and
// rosbag.hpp's bag format. Not a reimplementation of ros2's actual
// CLI or its bag format -- see rosbag.hpp's header comment for what's
// deliberately different and why.
//
// Usage:
//   commsys_bag record -o FILE [--registry NAME] [--transport shm|udp]
//                       [--duration SECONDS] TOPIC [TOPIC ...]
//   commsys_bag play FILE [--registry NAME] [--transport shm|udp]
//                    [--rate R] [--loop]
//   commsys_bag info FILE
#include "../include/node.hpp"
#include "../include/rosbag.hpp"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <csignal>
#include <cstdio>
#include <map>
#include <string>
#include <vector>

using namespace commsys;

namespace {

// Set by the SIGINT handler, checked in record's spin loop -- the
// same "run until Ctrl+C" shape `ros2 bag record` has, since a
// recorder's whole point is running for an open-ended session length
// the operator decides live, not a duration baked in ahead of time
// (--duration is offered too, for scripted/test use).
std::atomic<bool> g_stop{false};
void handle_sigint(int) { g_stop = true; }

void print_usage() {
    fprintf(stderr,
        "commsys_bag -- record, play back, and inspect commsys topic sessions\n\n"
        "Usage:\n"
        "  commsys_bag record -o FILE [--registry NAME] [--transport shm|udp]\n"
        "                      [--duration SECONDS] TOPIC [TOPIC ...]\n"
        "  commsys_bag play FILE [--registry NAME] [--transport shm|udp]\n"
        "                   [--rate R] [--loop]\n"
        "  commsys_bag info FILE\n");
}

std::string human_duration(double seconds) {
    char buf[64];
    if (seconds < 60) snprintf(buf, sizeof(buf), "%.2fs", seconds);
    else snprintf(buf, sizeof(buf), "%dm%.1fs", (int)(seconds / 60), fmod(seconds, 60.0));
    return buf;
}

int cmd_record(const std::vector<std::string>& args) {
    std::string out_path, registry = REGISTRY_NAME, transport;
    double duration_s = -1;  // -1 = run until SIGINT
    std::vector<std::string> topics;

    for (size_t i = 0; i < args.size(); i++) {
        const std::string& a = args[i];
        if (a == "-o" && i + 1 < args.size()) out_path = args[++i];
        else if (a == "--registry" && i + 1 < args.size()) registry = args[++i];
        else if (a == "--transport" && i + 1 < args.size()) transport = args[++i];
        else if (a == "--duration" && i + 1 < args.size()) duration_s = std::stod(args[++i]);
        else if (!a.empty() && a[0] != '-') topics.push_back(a);
        else { fprintf(stderr, "unrecognized argument: %s\n", a.c_str()); return 2; }
    }
    if (out_path.empty() || topics.empty()) {
        fprintf(stderr, "record requires -o FILE and at least one TOPIC\n");
        print_usage();
        return 2;
    }

    rosbag::BagWriter writer(out_path);
    NodeOptions opts;
    opts.force_transport = transport;
    opts.registry_name = registry;
    Node node("commsys_bag_record", opts);
    node.start();

    for (auto& topic : topics) {
        node.subscribe(topic, [&writer, topic](const uint8_t* data, uint32_t len) {
            auto now = std::chrono::system_clock::now().time_since_epoch();
            uint64_t ts = std::chrono::duration_cast<std::chrono::nanoseconds>(now).count();
            // type_name is unknown at this layer (raw bytes in, raw
            // bytes out) -- recorded as "unknown", same as any bag/
            // capture tool that doesn't have IDL introspection
            // available for an arbitrary topic. commsys_bag info
            // still reports accurate per-topic message counts and
            // timing regardless.
            writer.write_message(topic, "unknown", ts, data, len);
        });
    }

    fprintf(stderr, "[commsys_bag record] recording %zu topic(s) to %s ", topics.size(), out_path.c_str());
    for (auto& t : topics) fprintf(stderr, "%s ", t.c_str());
    fprintf(stderr, "\n[commsys_bag record] press Ctrl+C to stop%s\n",
            duration_s > 0 ? (" (or wait " + human_duration(duration_s) + ")").c_str() : "");

    std::signal(SIGINT, handle_sigint);
    auto start = std::chrono::steady_clock::now();
    while (!g_stop) {
        node.spin_once(50);
        if (duration_s > 0) {
            double elapsed = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
            if (elapsed >= duration_s) break;
        }
    }

    writer.close();
    node.stop();
    fprintf(stderr, "[commsys_bag record] wrote %llu message(s) to %s\n",
            (unsigned long long)writer.message_count(), out_path.c_str());
    return 0;
}

int cmd_play(const std::vector<std::string>& args) {
    std::string bag_path, registry = REGISTRY_NAME, transport;
    double rate = 1.0;
    bool loop = false;

    for (size_t i = 0; i < args.size(); i++) {
        const std::string& a = args[i];
        if (a == "--registry" && i + 1 < args.size()) registry = args[++i];
        else if (a == "--transport" && i + 1 < args.size()) transport = args[++i];
        else if (a == "--rate" && i + 1 < args.size()) rate = std::stod(args[++i]);
        else if (a == "--loop") loop = true;
        else if (!a.empty() && a[0] != '-') bag_path = a;
        else { fprintf(stderr, "unrecognized argument: %s\n", a.c_str()); return 2; }
    }
    if (bag_path.empty()) { fprintf(stderr, "play requires a bag FILE\n"); print_usage(); return 2; }

    rosbag::BagReader reader(bag_path);
    std::map<uint32_t, std::string> id_to_topic;
    std::vector<rosbag::MessageRecord> messages;
    reader.for_each_record(
        [&](const rosbag::Connection& c) { id_to_topic[c.topic_id] = c.topic_name; },
        [&](const rosbag::MessageRecord& m) { messages.push_back(m); });

    if (messages.empty()) { fprintf(stderr, "[commsys_bag play] bag has no messages\n"); return 0; }
    std::sort(messages.begin(), messages.end(),
              [](const rosbag::MessageRecord& a, const rosbag::MessageRecord& b) {
                  return a.timestamp_ns < b.timestamp_ns;
              });

    NodeOptions opts;
    opts.force_transport = transport;
    opts.registry_name = registry;
    Node node("commsys_bag_play", opts);
    node.start();
    for (auto& [id, name] : id_to_topic) node.advertise(name);
    node.spin_for(std::chrono::milliseconds(800));  // let discovery settle before the first publish

    fprintf(stderr, "[commsys_bag play] playing %zu message(s) across %zu topic(s) from %s, rate=%.2fx%s\n",
            messages.size(), id_to_topic.size(), bag_path.c_str(), rate, loop ? " (looping)" : "");

    std::signal(SIGINT, handle_sigint);
    do {
        uint64_t base_ts = messages.front().timestamp_ns;
        auto play_start = std::chrono::steady_clock::now();
        for (auto& m : messages) {
            if (g_stop) break;
            double target_offset_s = (double)(m.timestamp_ns - base_ts) / 1e9 / rate;
            auto target_time = play_start + std::chrono::duration_cast<std::chrono::steady_clock::duration>(
                                                 std::chrono::duration<double>(target_offset_s));
            while (std::chrono::steady_clock::now() < target_time && !g_stop) node.spin_once(1);

            auto it = id_to_topic.find(m.topic_id);
            if (it == id_to_topic.end()) continue;
            node.publish(it->second, m.payload.data(), (uint32_t)m.payload.size());
        }
    } while (loop && !g_stop);

    node.spin_for(std::chrono::milliseconds(300));
    node.stop();
    fprintf(stderr, "[commsys_bag play] done\n");
    return 0;
}

int cmd_info(const std::vector<std::string>& args) {
    if (args.empty()) { fprintf(stderr, "info requires a bag FILE\n"); print_usage(); return 2; }
    rosbag::BagReader reader(args[0]);
    auto s = reader.summarize();

    double duration_s = s.total_messages ? (double)(s.end_ns - s.start_ns) / 1e9 : 0.0;
    printf("Bag: %s\n", args[0].c_str());
    printf("Duration: %s\n", human_duration(duration_s).c_str());
    printf("Messages: %llu\n", (unsigned long long)s.total_messages);
    printf("Topics:\n");
    for (auto& [name, topic] : s.by_topic) {
        double hz = duration_s > 0 ? topic.count / duration_s : 0.0;
        printf("  %-30s type=%-25s count=%-8llu avg_hz=%.2f\n",
               name.c_str(), topic.type_name.c_str(), (unsigned long long)topic.count, hz);
    }
    return 0;
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 2) { print_usage(); return 2; }
    std::string cmd = argv[1];
    std::vector<std::string> args(argv + 2, argv + argc);

    try {
        if (cmd == "record") return cmd_record(args);
        if (cmd == "play") return cmd_play(args);
        if (cmd == "info") return cmd_info(args);
        fprintf(stderr, "unknown command: %s\n", cmd.c_str());
        print_usage();
        return 2;
    } catch (const std::exception& e) {
        fprintf(stderr, "commsys_bag: error: %s\n", e.what());
        return 1;
    }
}
