// discovery.hpp
//
// Direct port of discovery.py: a decentralized shared-memory table of
// active nodes and what topics they publish/subscribe. Any node
// attaches by well-known name; there is no central master process.
// Liveness is heartbeat-freshness AND a PID check (kill(pid,0)), so a
// crashed node that never unregistered is pruned quickly instead of
// leaving a stale entry.
#pragma once

#include <atomic>
#include <cstdint>
#include <cstring>
#include <chrono>
#include <optional>
#include <set>
#include <sstream>
#include <string>
#include <thread>
#include <vector>

#include <fcntl.h>
#include <signal.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#include <errno.h>

namespace commsys {

constexpr const char* REGISTRY_NAME = "/commsys_cpp_discovery";
constexpr int CAPACITY = 64;
constexpr int NODE_ID_LEN = 64;
constexpr int HOST_LEN = 64;
constexpr int TOPICS_LEN = 384;

#pragma pack(push, 1)
struct NodeSlot {
    uint8_t active;
    uint32_t pid;
    char node_id[NODE_ID_LEN];
    char host[HOST_LEN];
    uint32_t port;
    uint8_t transport_pref;  // 0=auto, 1=shm, 2=udp
    uint64_t last_heartbeat_ns;
    char topics[TOPICS_LEN];  // "pub=a,b|sub=c,~d" (~ prefix = keep_latest)
};
#pragma pack(pop)

struct NodeInfo {
    std::string node_id;
    std::string host;
    uint32_t port;
    std::set<std::string> published;
    std::set<std::string> subscribed;   // plain names, ~ stripped
    std::set<std::string> latest_topics;  // subset of subscribed wanting keep_latest
    uint32_t pid;
    uint8_t transport_pref;
};

inline uint64_t now_ns() {
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + ts.tv_nsec;
}

inline bool pid_alive(uint32_t pid) {
    if (pid == 0) return false;
    if (kill((pid_t)pid, 0) == 0) return true;
    return errno == EPERM;  // exists, just not signalable by us
}

inline std::string encode_topics(const std::set<std::string>& pub,
                                  const std::set<std::string>& sub,
                                  const std::set<std::string>& latest) {
    std::ostringstream oss;
    oss << "pub=";
    bool first = true;
    for (auto& t : pub) { if (!first) oss << ","; oss << t; first = false; }
    oss << "|sub=";
    first = true;
    for (auto& t : sub) {
        if (!first) oss << ",";
        if (latest.count(t)) oss << "~" << t; else oss << t;
        first = false;
    }
    return oss.str();
}

inline void decode_topics(const std::string& blob, std::set<std::string>& pub,
                           std::set<std::string>& sub, std::set<std::string>& latest) {
    pub.clear(); sub.clear(); latest.clear();
    size_t bar = blob.find('|');
    std::string pub_part = blob.substr(4, bar == std::string::npos ? std::string::npos : bar - 4);
    std::string sub_part = bar == std::string::npos ? "" : blob.substr(bar + 1 + 4);
    auto split = [](const std::string& s, auto&& fn) {
        size_t start = 0;
        if (s.empty()) return;
        while (start <= s.size()) {
            size_t comma = s.find(',', start);
            std::string tok = s.substr(start, comma == std::string::npos ? std::string::npos : comma - start);
            if (!tok.empty()) fn(tok);
            if (comma == std::string::npos) break;
            start = comma + 1;
        }
    };
    split(pub_part, [&](const std::string& t) { pub.insert(t); });
    split(sub_part, [&](const std::string& t) {
        if (!t.empty() && t[0] == '~') { sub.insert(t.substr(1)); latest.insert(t.substr(1)); }
        else sub.insert(t);
    });
}

class DiscoveryRegistry {
public:
    explicit DiscoveryRegistry(const std::string& name = REGISTRY_NAME) : name_(name) {
        size_t size = sizeof(NodeSlot) * CAPACITY;
        int fd = shm_open(name_.c_str(), O_CREAT | O_EXCL | O_RDWR, 0666);
        if (fd >= 0) {
            if (ftruncate(fd, (off_t)size) != 0) { close(fd); throw std::runtime_error("ftruncate failed"); }
            void* base = mmap(nullptr, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
            close(fd);
            if (base == MAP_FAILED) throw std::runtime_error("mmap failed");
            slots_ = reinterpret_cast<NodeSlot*>(base);
            // OS zero-fills a freshly extended segment; that's already
            // a valid "no nodes yet" state (active=0 everywhere), so
            // no explicit memset needed here -- see the Python
            // version's history for why an explicit zero-fill here
            // would actually be a race, not just redundant.
        } else {
            // Attach path: shm_open() succeeding here only means the
            // *name* exists, not that the creator has finished
            // ftruncate()-ing it to the right size yet -- those are
            // two separate, non-atomic steps. mmap()ing before that
            // completes and then touching the memory is a real SIGBUS,
            // not a theoretical one (hit it during testing). Wait for
            // the size to actually be there first, the same guard
            // ring_buffer.hpp and latest_value_slot.hpp already use.
            auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
            fd = shm_open(name_.c_str(), O_RDWR, 0666);
            if (fd < 0) throw std::runtime_error("discovery: cannot create or attach");
            struct stat st{};
            while (std::chrono::steady_clock::now() < deadline) {
                if (fstat(fd, &st) == 0 && st.st_size >= (off_t)size) break;
                std::this_thread::sleep_for(std::chrono::milliseconds(2));
            }
            if (st.st_size < (off_t)size) { close(fd); throw std::runtime_error("discovery segment never resized"); }
            void* base = mmap(nullptr, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
            close(fd);
            if (base == MAP_FAILED) throw std::runtime_error("mmap failed");
            slots_ = reinterpret_cast<NodeSlot*>(base);
        }
    }

    ~DiscoveryRegistry() { release(); }

    // Holds a raw mmap pointer with a non-trivial destructor (munmap).
    // The compiler-generated copy constructor would shallow-copy that
    // pointer and double-munmap on destruction of either copy -- a
    // real bug, not a theoretical one, since Node embeds a
    // DiscoveryRegistry as a member and anything that copies or
    // reallocates a Node (e.g. std::vector<Node> growing) would have
    // silently hit this. Move is safe and cheap (just transfers the
    // pointer), so support that instead.
    DiscoveryRegistry(const DiscoveryRegistry&) = delete;
    DiscoveryRegistry& operator=(const DiscoveryRegistry&) = delete;

    DiscoveryRegistry(DiscoveryRegistry&& other) noexcept
        : name_(std::move(other.name_)), slots_(other.slots_), my_slot_(other.my_slot_) {
        other.slots_ = nullptr;
    }
    DiscoveryRegistry& operator=(DiscoveryRegistry&& other) noexcept {
        if (this != &other) {
            release();
            name_ = std::move(other.name_);
            slots_ = other.slots_;
            my_slot_ = other.my_slot_;
            other.slots_ = nullptr;
        }
        return *this;
    }

    int register_node(const std::string& node_id, const std::string& host, uint32_t port,
                       const std::set<std::string>& pub, const std::set<std::string>& sub,
                       const std::set<std::string>& latest, uint8_t transport_pref = 0) {
        std::string blob = encode_topics(pub, sub, latest);
        for (int i = 0; i < CAPACITY; i++) {
            NodeSlot& slot = slots_[i];
            if (slot.active && pid_alive(slot.pid) && node_id != slot.node_id) continue;
            strncpy(slot.node_id, node_id.c_str(), NODE_ID_LEN - 1);
            slot.node_id[NODE_ID_LEN - 1] = 0;
            strncpy(slot.host, host.c_str(), HOST_LEN - 1);
            slot.host[HOST_LEN - 1] = 0;
            slot.port = port;
            slot.pid = (uint32_t)getpid();
            slot.transport_pref = transport_pref;
            strncpy(slot.topics, blob.c_str(), TOPICS_LEN - 1);
            slot.topics[TOPICS_LEN - 1] = 0;
            slot.last_heartbeat_ns = now_ns();
            slot.active = 1;
            my_slot_ = i;
            return i;
        }
        throw std::runtime_error("discovery registry full");
    }

    void heartbeat(int slot_idx, const std::set<std::string>& pub, const std::set<std::string>& sub,
                   const std::set<std::string>& latest) {
        NodeSlot& slot = slots_[slot_idx];
        std::string blob = encode_topics(pub, sub, latest);
        strncpy(slot.topics, blob.c_str(), TOPICS_LEN - 1);
        slot.topics[TOPICS_LEN - 1] = 0;
        slot.last_heartbeat_ns = now_ns();
    }

    void unregister(int slot_idx) { slots_[slot_idx].active = 0; }

    std::vector<NodeInfo> list_active(double ttl_sec = 2.0, int exclude_slot = -1) {
        std::vector<NodeInfo> result;
        uint64_t ttl_ns = (uint64_t)(ttl_sec * 1e9);
        uint64_t now = now_ns();
        for (int i = 0; i < CAPACITY; i++) {
            if (i == exclude_slot) continue;
            NodeSlot& slot = slots_[i];
            if (!slot.active) continue;
            if (now - slot.last_heartbeat_ns > ttl_ns) continue;
            if (!pid_alive(slot.pid)) continue;
            NodeInfo info;
            info.node_id = slot.node_id;
            info.host = slot.host;
            info.port = slot.port;
            info.pid = slot.pid;
            info.transport_pref = slot.transport_pref;
            decode_topics(slot.topics, info.published, info.subscribed, info.latest_topics);
            result.push_back(std::move(info));
        }
        return result;
    }

private:
    void release() {
        if (slots_) munmap(slots_, sizeof(NodeSlot) * CAPACITY);
        slots_ = nullptr;
    }

    std::string name_;
    NodeSlot* slots_ = nullptr;
    int my_slot_ = -1;
};

}  // namespace commsys
