// node.hpp
//
// Direct architectural port of node.py: advertise(topic),
// publish(topic, payload), subscribe(topic, callback[, keep_latest]).
// Peers found via DiscoveryRegistry; same dual shared-memory link
// design (FIFO RingBuffer vs LatestValueSlot per the subscriber's
// declared preference) plus best-effort chunked UDP for cross-host
// links.
//
// The key structural difference from the Python version, and the
// whole point of this port: there is no GIL and no asyncio task
// scheduler standing between "data is ready" and "the callback runs".
// The event loop here is a single-threaded epoll loop servicing the
// UDP socket and a small number of shared-memory poll timers; every
// iteration is native code with no interpreter dispatch overhead.
#pragma once

#include <arpa/inet.h>
#include <sched.h>
#include <sys/epoll.h>
#include <sys/socket.h>
#include <sys/timerfd.h>
#include <unistd.h>
#include <fcntl.h>

#include <cstring>
#include <chrono>
#include <functional>
#include <map>
#include <memory>
#include <set>
#include <string>
#include <vector>

#include "discovery.hpp"
#include "ring_buffer.hpp"
#include "latest_value_slot.hpp"

namespace commsys {

// ---- wire envelope: topic, seq, send_ns, sender_id, payload --------
struct EnvelopeHeader {
    uint16_t topic_len;
    uint32_t seq;
    uint64_t send_ns;
    uint16_t sender_len;
};

inline std::vector<uint8_t> pack_envelope(const std::string& topic, uint32_t seq, uint64_t send_ns,
                                           const std::string& sender, const uint8_t* payload, uint32_t payload_len) {
    EnvelopeHeader h{(uint16_t)topic.size(), seq, send_ns, (uint16_t)sender.size()};
    std::vector<uint8_t> buf(sizeof(h) + topic.size() + sender.size() + payload_len);
    size_t off = 0;
    memcpy(buf.data() + off, &h, sizeof(h)); off += sizeof(h);
    memcpy(buf.data() + off, topic.data(), topic.size()); off += topic.size();
    memcpy(buf.data() + off, sender.data(), sender.size()); off += sender.size();
    if (payload_len) memcpy(buf.data() + off, payload, payload_len);
    return buf;
}

// Same as pack_envelope, but writes into a reusable buffer instead of
// allocating a fresh one -- avoids a heap alloc/free pair on every
// single publish() call, which matters when publish() is called in a
// tight unpaced loop (hundreds of thousands of times per second).
inline void pack_envelope_into(std::vector<uint8_t>& out, const std::string& topic, uint32_t seq,
                                uint64_t send_ns, const std::string& sender,
                                const uint8_t* payload, uint32_t payload_len) {
    EnvelopeHeader h{(uint16_t)topic.size(), seq, send_ns, (uint16_t)sender.size()};
    size_t total = sizeof(h) + topic.size() + sender.size() + payload_len;
    if (out.capacity() < total) out.reserve(total * 2);  // amortize regrowth
    out.resize(total);
    size_t off = 0;
    memcpy(out.data() + off, &h, sizeof(h)); off += sizeof(h);
    memcpy(out.data() + off, topic.data(), topic.size()); off += topic.size();
    memcpy(out.data() + off, sender.data(), sender.size()); off += sender.size();
    if (payload_len) memcpy(out.data() + off, payload, payload_len);
}

struct UnpackedEnvelope {
    std::string topic;
    uint32_t seq;
    uint64_t send_ns;
    std::string sender;
    const uint8_t* payload;
    uint32_t payload_len;
};

inline UnpackedEnvelope unpack_envelope(const uint8_t* raw, uint32_t raw_len) {
    EnvelopeHeader h;
    memcpy(&h, raw, sizeof(h));
    size_t off = sizeof(h);
    std::string topic((const char*)raw + off, h.topic_len); off += h.topic_len;
    std::string sender((const char*)raw + off, h.sender_len); off += h.sender_len;
    return {topic, h.seq, h.send_ns, sender, raw + off, (uint32_t)(raw_len - off)};
}

// UDP chunk header, for the same reason transport.py chunks: a raw
// datagram over ~65KB fails outright, and on a real WiFi path
// (~1500B MTU) an unchunked large datagram risks IP fragmentation,
// where losing any one fragment loses the whole message.
struct ChunkHeader {
    uint32_t msg_id;
    uint16_t idx;
    uint16_t count;
};
constexpr size_t MAX_UDP_CHUNK = 1200;

struct SubStats {
    uint64_t count = 0;
    uint64_t drops = 0;
    uint64_t bytes_total = 0;
    std::vector<double> latencies_ms;
    std::map<std::string, uint32_t> last_seq_by_sender;
};

using Callback = std::function<void(const uint8_t*, uint32_t)>;

class Node {
public:
    Node(std::string node_id, std::string host = "127.0.0.1", uint16_t udp_port = 0,
         std::string force_transport = "", uint64_t shm_ring_capacity = 16 << 20,
         uint64_t shm_slot_capacity = 1 << 20, const std::string& registry_name = REGISTRY_NAME)
        : node_id_(std::move(node_id)), host_(std::move(host)), force_transport_(std::move(force_transport)),
          shm_ring_capacity_(shm_ring_capacity), shm_slot_capacity_(shm_slot_capacity),
          registry_(registry_name) {
        udp_port_requested_ = udp_port;
    }

    ~Node() { stop(); }

    void start() {
        epfd_ = epoll_create1(0);
        setup_udp_socket();

        std::set<std::string> empty;
        slot_ = registry_.register_node(node_id_, host_, udp_port_, published_, empty, empty,
                                         transport_pref_code());
        last_heartbeat_ = now();
        last_discovery_ = now();
    }

    void advertise(const std::string& topic) {
        published_.insert(topic);
        seq_by_topic_[topic] = 0;
    }

    void subscribe(const std::string& topic, Callback cb, bool keep_latest = false) {
        subscribed_[topic] = std::move(cb);
        stats_[topic] = SubStats{};
        if (keep_latest) keep_latest_topics_.insert(topic);
    }

    void publish(const std::string& topic, const uint8_t* payload, uint32_t len) {
        if (!published_.count(topic)) throw std::runtime_error("publish to un-advertised topic: " + topic);
        uint32_t seq = seq_by_topic_[topic]++;
        uint64_t send_ns = now_ns();
        pack_envelope_into(publish_scratch_, topic, seq, send_ns, node_id_, payload, len);
        const uint8_t* env_data = publish_scratch_.data();
        uint32_t env_len = (uint32_t)publish_scratch_.size();

        for (auto& [peer_id, link] : known_peers_) {
            if (!link.info.subscribed.count(topic)) continue;
            if (link.kind == LinkKind::Shm) {
                bool wants_latest = link.info.latest_topics.count(topic) != 0;
                if (wants_latest) {
                    auto it = out_slots_.find(peer_id);
                    if (it != out_slots_.end()) {
                        it->second.write(env_data, env_len);
                        sched_yield();
                    }
                } else {
                    auto it = out_rings_.find(peer_id);
                    if (it != out_rings_.end()) {
                        auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(50);
                        while (!it->second.try_write(env_data, env_len)) {
                            if (std::chrono::steady_clock::now() > deadline) break;
                        }
                    }
                }
            } else {  // UDP
                send_udp_chunked(env_data, env_len, link.info.host, link.info.port);
            }
        }
    }

    // Drives discovery polling, heartbeats, shm link polling, and UDP
    // receive, for up to `budget_ms`. Call this in a tight loop from
    // your own main() -- there is no hidden thread here.
    void spin_once(int budget_ms = 1) {
        poll_shm_links();
        poll_udp(0);  // non-blocking: don't let waiting for UDP traffic that
                       // may never come gate how often shm links get checked

        double t = now();
        if (t - last_heartbeat_ > HEARTBEAT_INTERVAL) {
            std::set<std::string> discovery_sub;
            for (auto& [topic, cb] : subscribed_) (void)cb, discovery_sub.insert(topic);
            registry_.heartbeat(slot_, published_, discovery_sub, keep_latest_topics_);
            last_heartbeat_ = t;
        }
        if (t - last_discovery_ > DISCOVERY_POLL_INTERVAL) {
            run_discovery();
            last_discovery_ = t;
        }
    }

    void stop() {
        for (auto& [id, r] : out_rings_) { r.mark_closed(); }
        for (auto& [id, s] : out_slots_) { s.mark_closed(); }
        for (auto& [id, r] : in_rings_) { r.mark_closed(); }
        for (auto& [id, s] : in_slots_) { s.mark_closed(); }
        if (slot_ >= 0) { registry_.unregister(slot_); slot_ = -1; }
        if (udp_fd_ >= 0) { close(udp_fd_); udp_fd_ = -1; }
        if (epfd_ >= 0) { close(epfd_); epfd_ = -1; }
    }

    SubStats& stats(const std::string& topic) { return stats_[topic]; }
    uint16_t udp_port() const { return udp_port_; }

private:
    enum class LinkKind { Shm, Udp };
    struct Link { LinkKind kind; NodeInfo info; };

    static double now() {
        return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
    }
    static uint64_t now_ns() { return commsys::now_ns(); }

    uint8_t transport_pref_code() const {
        if (force_transport_ == "shm") return 1;
        if (force_transport_ == "udp") return 2;
        return 0;
    }

    void setup_udp_socket() {
        udp_fd_ = socket(AF_INET, SOCK_DGRAM, 0);
        int opt = 1;
        setsockopt(udp_fd_, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
        int bufsz = 8 << 20;
        setsockopt(udp_fd_, SOL_SOCKET, SO_RCVBUF, &bufsz, sizeof(bufsz));
        setsockopt(udp_fd_, SOL_SOCKET, SO_SNDBUF, &bufsz, sizeof(bufsz));

        sockaddr_in addr{};
        addr.sin_family = AF_INET;
        addr.sin_port = htons(udp_port_requested_);
        inet_pton(AF_INET, host_.c_str(), &addr.sin_addr);
        if (bind(udp_fd_, (sockaddr*)&addr, sizeof(addr)) != 0)
            throw std::runtime_error("bind failed");
        socklen_t len = sizeof(addr);
        getsockname(udp_fd_, (sockaddr*)&addr, &len);
        udp_port_ = ntohs(addr.sin_port);

        int flags = fcntl(udp_fd_, F_GETFL, 0);
        fcntl(udp_fd_, F_SETFL, flags | O_NONBLOCK);

        epoll_event ev{};
        ev.events = EPOLLIN;
        ev.data.fd = udp_fd_;
        epoll_ctl(epfd_, EPOLL_CTL_ADD, udp_fd_, &ev);
    }

    void poll_udp(int budget_ms) {
        epoll_event events[8];
        int n = epoll_wait(epfd_, events, 8, budget_ms);
        for (int i = 0; i < n; i++) {
            uint8_t buf[65536];
            sockaddr_in from{};
            socklen_t fromlen = sizeof(from);
            while (true) {
                ssize_t r = recvfrom(udp_fd_, buf, sizeof(buf), 0, (sockaddr*)&from, &fromlen);
                if (r <= 0) break;
                handle_udp_datagram(buf, (uint32_t)r, from);
            }
        }
    }

    void handle_udp_datagram(const uint8_t* data, uint32_t len, const sockaddr_in& from) {
        ChunkHeader ch;
        memcpy(&ch, data, sizeof(ch));
        const uint8_t* chunk = data + sizeof(ch);
        uint32_t chunk_len = len - sizeof(ch);
        if (ch.count == 1) {
            dispatch(chunk, chunk_len);
            return;
        }
        uint64_t key = ((uint64_t)from.sin_addr.s_addr << 32) ^ ((uint64_t)from.sin_port << 16) ^ ch.msg_id;
        auto& parts = udp_reassembly_[key];
        parts.count = ch.count;
        if (parts.chunks.size() < ch.count) parts.chunks.resize(ch.count);
        parts.chunks[ch.idx].assign(chunk, chunk + chunk_len);
        parts.have++;
        if (parts.have == parts.count) {
            std::vector<uint8_t> full;
            for (auto& c : parts.chunks) full.insert(full.end(), c.begin(), c.end());
            udp_reassembly_.erase(key);
            dispatch(full.data(), (uint32_t)full.size());
        }
    }

    void send_udp_chunked(const uint8_t* envelope, uint32_t n, const std::string& host, uint16_t port) {
        sockaddr_in addr{};
        addr.sin_family = AF_INET;
        addr.sin_port = htons(port);
        inet_pton(AF_INET, host.c_str(), &addr.sin_addr);

        uint16_t count = (uint16_t)((n + MAX_UDP_CHUNK - 1) / MAX_UDP_CHUNK);
        if (count == 0) count = 1;
        uint32_t msg_id = udp_msg_id_counter_++;
        std::vector<uint8_t> pkt;
        for (uint16_t idx = 0; idx < count; idx++) {
            size_t start = idx * MAX_UDP_CHUNK;
            size_t clen = std::min(MAX_UDP_CHUNK, (size_t)n - start);
            ChunkHeader ch{msg_id, idx, count};
            pkt.resize(sizeof(ch) + clen);
            memcpy(pkt.data(), &ch, sizeof(ch));
            if (clen) memcpy(pkt.data() + sizeof(ch), envelope + start, clen);
            sendto(udp_fd_, pkt.data(), pkt.size(), 0, (sockaddr*)&addr, sizeof(addr));
        }
    }

    void dispatch(const uint8_t* raw, uint32_t len) {
        uint64_t recv_ns = now_ns();
        auto env = unpack_envelope(raw, len);
        auto it = subscribed_.find(env.topic);
        if (it == subscribed_.end()) return;
        auto& st = stats_[env.topic];
        st.count++;
        st.bytes_total += env.payload_len;
        st.latencies_ms.push_back((recv_ns - env.send_ns) / 1e6);
        auto sit = st.last_seq_by_sender.find(env.sender);
        if (sit != st.last_seq_by_sender.end() && env.seq != sit->second + 1 && env.seq > sit->second) {
            st.drops += env.seq - sit->second - 1;
        }
        st.last_seq_by_sender[env.sender] = env.seq;
        it->second(env.payload, env.payload_len);
    }

    void poll_shm_links() {
        static thread_local std::vector<uint8_t> buf(16 << 20);
        for (auto& [peer_id, ring] : in_rings_) {
            for (int i = 0; i < 64; i++) {  // drain a bounded batch per spin to stay fair
                int n = ring.try_read(buf.data());
                if (n < 0) break;
                dispatch(buf.data(), (uint32_t)n);
            }
        }
        for (auto& [peer_id, slot] : in_slots_) {
            uint64_t seq;
            int n = slot.try_read_versioned(buf.data(), seq);
            if (n < 0) continue;
            uint64_t& last = slot_last_seen_seq_[peer_id];
            if (seq == last) continue;  // no new write since last poll
            last = seq;
            dispatch(buf.data(), (uint32_t)n);
        }
    }

    bool use_shm(const NodeInfo& peer) const {
        uint8_t mypref = transport_pref_code();
        if (mypref == 2 || peer.transport_pref == 2) return false;
        return peer.host == host_;
    }

    void run_discovery() {
        auto peers = registry_.list_active(2.0, slot_);
        std::set<std::string> seen;
        for (auto& peer : peers) {
            seen.insert(peer.node_id);
            bool relevant = false;
            for (auto& t : published_) if (peer.subscribed.count(t)) { relevant = true; break; }
            if (!relevant) for (auto& [t, cb] : subscribed_) { (void)cb; if (peer.published.count(t)) { relevant = true; break; } }
            if (!relevant) continue;
            setup_link(peer);
        }
        std::vector<std::string> gone;
        for (auto& [id, link] : known_peers_) if (!seen.count(id)) gone.push_back(id);
        for (auto& id : gone) teardown_link(id);
    }

    void setup_link(const NodeInfo& peer) {
        LinkKind kind = use_shm(peer) ? LinkKind::Shm : LinkKind::Udp;
        known_peers_[peer.node_id] = {kind, peer};
        if (kind != LinkKind::Shm) return;

        std::set<std::string> shared_out;
        for (auto& t : published_) if (peer.subscribed.count(t)) shared_out.insert(t);
        bool any_fifo_out = false, any_latest_out = false;
        for (auto& t : shared_out) (peer.latest_topics.count(t) ? any_latest_out : any_fifo_out) = true;

        if (any_fifo_out && !out_rings_.count(peer.node_id)) {
            out_rings_.emplace(peer.node_id, RingBuffer::create(
                link_ring_name(node_id_, peer.node_id), shm_ring_capacity_));
        }
        if (any_latest_out && !out_slots_.count(peer.node_id)) {
            out_slots_.emplace(peer.node_id, LatestValueSlot::create(
                link_slot_name(node_id_, peer.node_id), shm_slot_capacity_));
        }

        std::set<std::string> shared_in;
        for (auto& [t, cb] : subscribed_) { (void)cb; if (peer.published.count(t)) shared_in.insert(t); }
        bool any_fifo_in = false, any_latest_in = false;
        for (auto& t : shared_in) (keep_latest_topics_.count(t) ? any_latest_in : any_fifo_in) = true;

        if (any_fifo_in && !in_rings_.count(peer.node_id)) {
            try {
                in_rings_.emplace(peer.node_id, RingBuffer::attach(link_ring_name(peer.node_id, node_id_), 0.2));
            } catch (...) { /* publisher hasn't created it yet; next discovery pass retries */ }
        }
        if (any_latest_in && !in_slots_.count(peer.node_id)) {
            try {
                in_slots_.emplace(peer.node_id, LatestValueSlot::attach(link_slot_name(peer.node_id, node_id_), 0.2));
            } catch (...) { /* same */ }
        }
    }

    void teardown_link(const std::string& peer_id) {
        known_peers_.erase(peer_id);
        out_rings_.erase(peer_id);
        out_slots_.erase(peer_id);
        in_rings_.erase(peer_id);
        in_slots_.erase(peer_id);
        slot_last_seen_seq_.erase(peer_id);
    }

    static std::string link_ring_name(const std::string& pub, const std::string& sub) {
        return "/commsys_cpp_link_" + pub + "_" + sub;
    }
    static std::string link_slot_name(const std::string& pub, const std::string& sub) {
        return "/commsys_cpp_slot_" + pub + "_" + sub;
    }

    static constexpr double HEARTBEAT_INTERVAL = 0.5;
    static constexpr double DISCOVERY_POLL_INTERVAL = 0.15;

    std::string node_id_, host_, force_transport_;
    uint16_t udp_port_requested_ = 0, udp_port_ = 0;
    uint64_t shm_ring_capacity_, shm_slot_capacity_;
    DiscoveryRegistry registry_;
    int slot_ = -1;
    int epfd_ = -1, udp_fd_ = -1;
    double last_heartbeat_ = 0, last_discovery_ = 0;

    std::set<std::string> published_;
    std::map<std::string, Callback> subscribed_;
    std::set<std::string> keep_latest_topics_;
    std::map<std::string, uint32_t> seq_by_topic_;
    std::map<std::string, SubStats> stats_;

    std::map<std::string, Link> known_peers_;
    std::map<std::string, RingBuffer> out_rings_, in_rings_;
    std::map<std::string, LatestValueSlot> out_slots_, in_slots_;
    std::map<std::string, uint64_t> slot_last_seen_seq_;

    uint32_t udp_msg_id_counter_ = 1;
    std::vector<uint8_t> publish_scratch_;
    struct Reassembly { std::vector<std::vector<uint8_t>> chunks; uint16_t count = 0, have = 0; };
    std::map<uint64_t, Reassembly> udp_reassembly_;
};

}  // namespace commsys
