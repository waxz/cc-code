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
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include "discovery.hpp"
#include "ring_buffer.hpp"
#include "latest_value_slot.hpp"
#include "message_traits.hpp"

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

// All exceptions thrown directly by Node (as opposed to exceptions
// that might propagate up from things it calls, like std::bad_alloc)
// use this type, so callers can catch commsys errors specifically
// without also catching unrelated standard-library exceptions.
class NodeError : public std::runtime_error {
public:
    explicit NodeError(const std::string& what) : std::runtime_error(what) {}
};

// Construction options for Node, grouped into one struct instead of a
// long positional parameter list. Every field has a sensible default,
// so `Node("my_node")` alone is a complete, valid construction --
// override only the fields that matter for a given use case, e.g.:
//
//   Node n("lidar_node", {.force_transport = "shm",
//                          .shm_ring_capacity = 32 << 20});
//
// (designated initializers, C++20; for C++17 use
//  NodeOptions opts; opts.force_transport = "shm"; Node n("id", opts);)
struct NodeOptions {
    std::string host = "127.0.0.1";
    uint16_t udp_port = 0;          // 0 = let the OS pick a free port
    std::string force_transport;     // "", "shm", or "udp"; "" = auto-select per peer

    // Shared-memory link sizing. See node.hpp's design notes and
    // cpp/CPP_PORT_REPORT.md for why the defaults are what they are:
    // large enough to hold a burst of the biggest realistic message
    // (a LiDAR-scan-sized payload) without the publisher spending most
    // of its time backoff-spinning waiting for the subscriber to
    // drain, but not so large that first-touch page faults on a
    // freshly created ring become their own cost.
    uint64_t shm_ring_capacity = 16 << 20;
    uint64_t shm_slot_capacity = 1 << 20;

    // Override only for test isolation (running multiple independent
    // "networks" of nodes in the same process/test suite) or if you
    // deliberately want a private discovery domain. Nodes with
    // different registry_name values cannot discover each other.
    std::string registry_name = REGISTRY_NAME;
};

class Node {
public:
    /// Preferred constructor: see NodeOptions for what each field
    /// means and its default. `node_id` must be unique across every
    /// node sharing the same discovery domain (registry_name) --
    /// two nodes registering with the same id will overwrite each
    /// other's discovery record.
    Node(std::string node_id, const NodeOptions& options = {})
        : node_id_(std::move(node_id)), host_(options.host), force_transport_(options.force_transport),
          shm_ring_capacity_(options.shm_ring_capacity), shm_slot_capacity_(options.shm_slot_capacity),
          registry_(options.registry_name) {
        udp_port_requested_ = options.udp_port;
    }

    /// Legacy positional constructor, kept for existing call sites.
    /// Prefer the NodeOptions overload for new code -- it's harder to
    /// accidentally pass an argument in the wrong position (e.g.
    /// registry_name where you meant shm_slot_capacity).
    Node(std::string node_id, std::string host, uint16_t udp_port,
         std::string force_transport, uint64_t shm_ring_capacity = 16 << 20,
         uint64_t shm_slot_capacity = 1 << 20, const std::string& registry_name = REGISTRY_NAME)
        : node_id_(std::move(node_id)), host_(std::move(host)), force_transport_(std::move(force_transport)),
          shm_ring_capacity_(shm_ring_capacity), shm_slot_capacity_(shm_slot_capacity),
          registry_(registry_name) {
        udp_port_requested_ = udp_port;
    }

    Node(const Node&) = delete;
    Node& operator=(const Node&) = delete;

    // A defaulted move would be wrong here, not just suboptimal: this
    // class has a user-declared destructor and owns raw OS handles
    // (epfd_, udp_fd_) plus a discovery slot index (slot_). A
    // member-wise default move copies those primitive ints as-is
    // without resetting them in the source object, so both the moved-
    // from and moved-to Node would believe they own the same fds/slot
    // -- and when the moved-from object's destructor runs stop(), it
    // would close/unregister resources the moved-to object still
    // actively uses. Written out explicitly instead, matching the
    // same pattern RingBuffer/LatestValueSlot/DiscoveryRegistry
    // already use for exactly this reason.
    Node(Node&& other) noexcept
        : node_id_(std::move(other.node_id_)), host_(std::move(other.host_)),
          force_transport_(std::move(other.force_transport_)),
          udp_port_requested_(other.udp_port_requested_), udp_port_(other.udp_port_),
          shm_ring_capacity_(other.shm_ring_capacity_), shm_slot_capacity_(other.shm_slot_capacity_),
          registry_(std::move(other.registry_)), slot_(other.slot_), epfd_(other.epfd_), udp_fd_(other.udp_fd_),
          started_(other.started_), last_heartbeat_(other.last_heartbeat_), last_discovery_(other.last_discovery_),
          published_(std::move(other.published_)), subscribed_(std::move(other.subscribed_)),
          keep_latest_topics_(std::move(other.keep_latest_topics_)), seq_by_topic_(std::move(other.seq_by_topic_)),
          stats_(std::move(other.stats_)), known_peers_(std::move(other.known_peers_)),
          out_rings_(std::move(other.out_rings_)), in_rings_(std::move(other.in_rings_)),
          out_slots_(std::move(other.out_slots_)), in_slots_(std::move(other.in_slots_)),
          slot_last_seen_seq_(std::move(other.slot_last_seen_seq_)),
          udp_msg_id_counter_(other.udp_msg_id_counter_), publish_scratch_(std::move(other.publish_scratch_)),
          udp_reassembly_(std::move(other.udp_reassembly_)) {
        other.slot_ = -1;
        other.epfd_ = -1;
        other.udp_fd_ = -1;
        other.started_ = false;
    }
    Node& operator=(Node&& other) noexcept {
        if (this == &other) return *this;
        stop();  // release whatever *this currently holds first

        node_id_ = std::move(other.node_id_);
        host_ = std::move(other.host_);
        force_transport_ = std::move(other.force_transport_);
        udp_port_requested_ = other.udp_port_requested_;
        udp_port_ = other.udp_port_;
        shm_ring_capacity_ = other.shm_ring_capacity_;
        shm_slot_capacity_ = other.shm_slot_capacity_;
        registry_ = std::move(other.registry_);
        slot_ = other.slot_;
        epfd_ = other.epfd_;
        udp_fd_ = other.udp_fd_;
        started_ = other.started_;
        last_heartbeat_ = other.last_heartbeat_;
        last_discovery_ = other.last_discovery_;
        published_ = std::move(other.published_);
        subscribed_ = std::move(other.subscribed_);
        keep_latest_topics_ = std::move(other.keep_latest_topics_);
        seq_by_topic_ = std::move(other.seq_by_topic_);
        stats_ = std::move(other.stats_);
        known_peers_ = std::move(other.known_peers_);
        out_rings_ = std::move(other.out_rings_);
        in_rings_ = std::move(other.in_rings_);
        out_slots_ = std::move(other.out_slots_);
        in_slots_ = std::move(other.in_slots_);
        slot_last_seen_seq_ = std::move(other.slot_last_seen_seq_);
        udp_msg_id_counter_ = other.udp_msg_id_counter_;
        publish_scratch_ = std::move(other.publish_scratch_);
        udp_reassembly_ = std::move(other.udp_reassembly_);

        // Reset the source's handles so its destructor's stop() is a
        // no-op instead of tearing down what *this now owns.
        other.slot_ = -1;
        other.epfd_ = -1;
        other.udp_fd_ = -1;
        other.started_ = false;
        return *this;
    }

    ~Node() { stop(); }

    /// Binds the UDP socket, registers with discovery, and makes this
    /// node visible to every other node sharing the same discovery
    /// domain. Call advertise()/subscribe() either before or after
    /// start() -- both orders work, since topic changes propagate to
    /// peers via the next heartbeat regardless of when they're made.
    /// Throws NodeError if the UDP socket can't be bound (e.g. a
    /// specific requested port is already in use).
    void start() {
        epfd_ = epoll_create1(0);
        setup_udp_socket();

        std::set<std::string> empty;
        slot_ = registry_.register_node(node_id_, host_, udp_port_, published_, empty, empty,
                                         transport_pref_code());
        last_heartbeat_ = now();
        last_discovery_ = now();
        started_ = true;
    }

    bool is_started() const { return started_; }

    /// Declares this node as a publisher of `topic`. Must be called
    /// before publish() on that topic (publish() to an un-advertised
    /// topic throws NodeError). Safe to call before or after start().
    void advertise(const std::string& topic) {
        published_.insert(topic);
        seq_by_topic_[topic] = 0;
    }

    /// Raw-bytes subscribe: `cb` is invoked with a pointer valid only
    /// for the duration of the call -- copy out anything you need to
    /// keep. For type-safe subscription to a POD struct or a
    /// pre-serialized (e.g. FlatBuffers) buffer, prefer the templated
    /// subscribe<T>() overload below instead.
    ///
    /// keep_latest=true: bounded-staleness delivery via a lock-free
    /// single-slot primitive instead of the default FIFO ring -- the
    /// right choice for a live sensor feed driving a control loop
    /// (IMU, pose), where a slow subscriber should see the freshest
    /// sample instead of working through a backlog. See
    /// shared_memory_ipc.py's / latest_value_slot.hpp's design notes
    /// and cpp/CPP_PORT_REPORT.md for the measured latency difference
    /// this makes under load.
    void subscribe(const std::string& topic, Callback cb, bool keep_latest = false) {
        subscribed_[topic] = std::move(cb);
        stats_[topic] = SubStats{};
        if (keep_latest) keep_latest_topics_.insert(topic);
    }

    /// Type-safe subscribe: the callback receives a `const T&` instead
    /// of raw bytes. T must either be trivially copyable (the default
    /// zero-copy path, right for small POD messages like IMU/encoder
    /// samples) or have an explicit MessageTraits<T> specialization
    /// (e.g. RawBytes for a pre-serialized FlatBuffers buffer). T is
    /// deduced from the callback's argument type when possible, but
    /// explicit instantiation (`node.subscribe<ImuSample>(...)`) is
    /// recommended for clarity at the call site.
    template <typename T, typename F>
    void subscribe(const std::string& topic, F&& cb, bool keep_latest = false) {
        subscribe(topic, Callback([cb = std::forward<F>(cb)](const uint8_t* data, uint32_t len) {
            cb(MessageTraits<T>::deserialize(data, len));
        }), keep_latest);
    }

    /// Raw-bytes publish. `payload` is copied into the wire envelope
    /// before this call returns, so it's safe to reuse/free
    /// immediately after. Throws NodeError if `topic` wasn't
    /// advertise()'d first.
    void publish(const std::string& topic, const uint8_t* payload, uint32_t len) {
        if (!published_.count(topic))
            throw NodeError("publish() to un-advertised topic " + topic +
                             " on node " + node_id_ + " -- call advertise(\"" + topic +
                             "\") first");
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
                            // Same fix as the keep_latest slot write
                            // path, and the same real bug class as
                            // node.py's original blocking time.sleep()
                            // in the ring backoff: this loop makes zero
                            // syscalls otherwise, so nothing gives the
                            // OS scheduler a natural opportunity to run
                            // the consumer process while the ring is
                            // full. Confirmed via direct measurement
                            // (not guessed) to be the actual cause of a
                            // persistent ~300ms max-latency outlier that
                            // survived even a 4-vCPU rerun -- ruling out
                            // both page faults (measured at ~14ms for
                            // the full ring, an order of magnitude too
                            // small) and heap allocation as explanations.
                            sched_yield();
                        }
                    }
                }
            } else {  // UDP
                send_udp_chunked(env_data, env_len, link.info.host, link.info.port);
            }
        }
    }

    /// Type-safe publish: accepts any T with a MessageTraits<T>
    /// (trivially-copyable POD structs work automatically; use
    /// RawBytes to publish an already-serialized buffer). T is
    /// deduced from `message`'s type.
    template <typename T>
    void publish(const std::string& topic, const T& message) {
        publish(topic, MessageTraits<T>::data(message), MessageTraits<T>::size(message));
    }

    /// Drives discovery polling, heartbeats, shm link polling, and UDP
    /// receive, for up to `budget_ms`. Call this in a tight loop from
    /// your own main() -- there is no hidden thread here.
    ///
    /// IMPORTANT: call this periodically even inside a long-running,
    /// otherwise-tight publish loop, not just from a subscriber's
    /// loop. spin_once() is what sends this node's own heartbeat --
    /// skip it for longer than the discovery TTL and *other* nodes
    /// will conclude this one has died and tear down their links to
    /// it, even though it's still actively publishing. This was a
    /// real, measured bug (see cpp/CPP_PORT_REPORT.md and the ~300ms
    /// latency investigation), not a hypothetical footgun -- prefer
    /// spin_for() below for exactly this reason.
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

    /// Convenience wrapper: call spin_once() in a loop for `duration`.
    /// This is the pattern every test/benchmark in this project
    /// hand-rolled independently (`while (now() < t_end) spin_once();`)
    /// -- provided here once, correctly, instead of leaving every
    /// caller to reimplement it (and potentially forget to call it at
    /// all inside a tight publish loop, which is exactly the bug
    /// spin_once()'s docs above warn about).
    void spin_for(std::chrono::steady_clock::duration duration, int budget_ms = 1) {
        auto deadline = std::chrono::steady_clock::now() + duration;
        while (std::chrono::steady_clock::now() < deadline) spin_once(budget_ms);
    }

    /// Like spin_for(), but for a publish loop: calls `publish_fn`
    /// repeatedly, and periodically calls spin_once() in between
    /// (every `spin_every` calls) so this node's own heartbeat and
    /// discovery bookkeeping keep running even inside a tight, fast
    /// publish loop. This is the direct fix for the spin_once()
    /// warning above, applied automatically instead of left as
    /// something every caller has to remember.
    template <typename F>
    void publish_loop_for(std::chrono::steady_clock::duration duration, F&& publish_fn,
                           unsigned spin_every = 256) {
        auto deadline = std::chrono::steady_clock::now() + duration;
        unsigned count = 0;
        while (std::chrono::steady_clock::now() < deadline) {
            publish_fn();
            if ((++count % spin_every) == 0) spin_once(0);
        }
    }

    /// Unregisters from discovery, closes all links and the UDP
    /// socket. Safe to call multiple times (idempotent) and safe to
    /// skip -- the destructor calls this automatically.
    void stop() {
        for (auto& [id, r] : out_rings_) { r.mark_closed(); }
        for (auto& [id, s] : out_slots_) { s.mark_closed(); }
        for (auto& [id, r] : in_rings_) { r.mark_closed(); }
        for (auto& [id, s] : in_slots_) { s.mark_closed(); }
        if (slot_ >= 0) { registry_.unregister(slot_); slot_ = -1; }
        if (udp_fd_ >= 0) { close(udp_fd_); udp_fd_ = -1; }
        if (epfd_ >= 0) { close(epfd_); epfd_ = -1; }
        started_ = false;
    }

    /// Delivery/latency statistics for a subscribed topic (count,
    /// drops, byte total, per-message latency samples). Returns a
    /// reference to an internal, growing structure -- see
    /// cpp/CPP_PORT_REPORT.md's notes on SubStats::latencies_ms for
    /// the known unbounded-growth caveat in a long-running deployment.
    SubStats& stats(const std::string& topic) { return stats_[topic]; }

    /// The UDP port this node actually bound to -- useful when
    /// NodeOptions::udp_port was left at 0 (OS picks a free port) and
    /// something else needs to know which port was chosen.
    uint16_t udp_port() const { return udp_port_; }

    const std::string& node_id() const { return node_id_; }

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
        // TTL is deliberately generous (not the more obvious ~2x
        // heartbeat interval). Root-caused via direct measurement: a
        // caller with a tight, unpaced publish loop that doesn't also
        // call spin_once() periodically silently lets its own
        // heartbeat go stale, since heartbeat sending and discovery
        // polling both live inside spin_once(). With a tight TTL, a
        // peer's link gets torn down mid-firehose and has to
        // reconnect and drain whatever backlog piled up in the
        // meantime -- this was confirmed to be the actual cause of a
        // persistent ~300ms max-latency outlier in exactly that
        // scenario (see bench/test_ring_stress.cpp's history), not
        // page faults or heap allocation as originally suspected. A
        // generous TTL is a mitigation, not a structural fix: any
        // caller whose publish-only loop runs longer than the TTL
        // without calling spin_once() will eventually hit this again.
        // Call spin_once() periodically even inside a tight publish
        // loop (see test_ring_stress.cpp / test_node_udp_latest.cpp
        // for the pattern) -- that's the actual fix.
        auto peers = registry_.list_active(10.0, slot_);
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
    bool started_ = false;
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
