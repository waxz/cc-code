// ros_compat.hpp
//
// An rclcpp-shaped API over commsys::Node, for code that wants to
// read (and be easy to port to/from) something ROS2-familiar:
// create_publisher<T>()/create_subscription<T>(), a QoS object,
// spin()/spin_some(). This is a thin adapter, not a reimplementation
// -- every call here delegates straight to the underlying, already-
// tested commsys::Node API (see node.hpp/API_GUIDE.md). Composition,
// not inheritance: ros_compat::Node HAS a commsys::Node rather than
// IS one, so there's no risk of someone deleting through a
// non-virtual base pointer, and the two APIs stay cleanly separated
// instead of both being visible (and possibly confused for each
// other) on the same object.
//
// What this deliberately does NOT attempt: DDS-level QoS (deadline,
// liveliness, durability policies), parameters, services/actions, tf,
// or any of rclcpp's much larger surface. Publish/subscribe with a
// QoS depth is the part of the ROS2 API this project's design
// actually has an equivalent for (FIFO ring vs keep_latest slot);
// pretending to support the rest would be misleading.
//
// Mapping from ROS2 QoS to commsys's two real delivery models:
//   depth <= 1  -> keep_latest slot (bounded staleness, ROS2's
//                  "keep last 1" is conceptually the same idea)
//   depth  > 1  -> FIFO ring (every message, in order; commsys's ring
//                  is byte-capacity-bounded rather than message-count
//                  bounded, so "depth" here is advisory, not an exact
//                  queue-length guarantee the way DDS's is)
#pragma once

#include "node.hpp"
#include <functional>
#include <memory>
#include <string>
#include <utility>

namespace commsys {
namespace ros_compat {

class QoS {
public:
    explicit QoS(size_t depth = 10) : depth_(depth) {}

    QoS& keep_last(size_t depth) { depth_ = depth; return *this; }
    QoS& best_effort() { reliable_ = false; return *this; }
    QoS& reliable() { reliable_ = true; return *this; }

    size_t depth() const { return depth_; }
    bool is_reliable() const { return reliable_; }
    /// See the file-level comment: depth<=1 maps to the keep_latest
    /// slot, matching ROS2's "keep last 1" QoS depth.
    bool wants_keep_latest() const { return depth_ <= 1; }

private:
    size_t depth_;
    bool reliable_ = true;
};

// Convenience QoS presets matching rclcpp's commonly-used named
// profiles (rclcpp::SensorDataQoS(), rclcpp::SystemDefaultsQoS()).
inline QoS SensorDataQoS() { return QoS(1).best_effort(); }
inline QoS SystemDefaultsQoS() { return QoS(10).reliable(); }

template <typename T>
class Publisher {
public:
    Publisher(commsys::Node& node, std::string topic) : node_(node), topic_(std::move(topic)) {}
    void publish(const T& msg) { node_.publish(topic_, msg); }
    const std::string& get_topic_name() const { return topic_; }

private:
    commsys::Node& node_;
    std::string topic_;
};

// Stateless handle -- commsys::Node owns the actual subscription
// state internally (see subscribe<T>() in node.hpp), so there is
// nothing for this object to hold beyond the topic name. Exists
// mainly so create_subscription()'s return type reads the way
// rclcpp's does, and so a caller has something to keep a shared_ptr
// to if they want the subscription to visually "stay alive" the way
// an rclcpp::Subscription does (even though nothing would actually
// break here if it were dropped -- the callback is already
// registered on the Node).
template <typename T>
class Subscription {
public:
    explicit Subscription(std::string topic) : topic_(std::move(topic)) {}
    const std::string& get_topic_name() const { return topic_; }

private:
    std::string topic_;
};

/// rclcpp::Node-shaped wrapper around commsys::Node. Construct via
/// make_node() below (mirrors rclcpp::Node::make_shared /
/// rclcpp_components patterns) rather than directly, so start() is
/// guaranteed to have been called before you can get a NodePtr to use.
class Node {
public:
    explicit Node(std::string node_id, const NodeOptions& options = {})
        : impl_(std::move(node_id), options) {}

    template <typename T>
    std::shared_ptr<Publisher<T>> create_publisher(const std::string& topic, const QoS& qos = QoS()) {
        (void)qos;  // publish()-side QoS doesn't change wire behavior in commsys's
                    // model -- it's the *subscriber's* QoS that picks ring vs slot,
                    // same as how a DDS publisher doesn't know its subscribers'
                    // history/durability settings either.
        impl_.advertise(topic);
        return std::make_shared<Publisher<T>>(impl_, topic);
    }

    template <typename T, typename Callback>
    std::shared_ptr<Subscription<T>> create_subscription(const std::string& topic, const QoS& qos,
                                                           Callback&& cb) {
        impl_.subscribe<T>(topic, std::forward<Callback>(cb), qos.wants_keep_latest());
        return std::make_shared<Subscription<T>>(topic);
    }

    /// Raw-bytes overload, for parity with commsys::Node's own raw API.
    std::shared_ptr<Subscription<RawBytes>> create_subscription(const std::string& topic, const QoS& qos,
                                                                  Callback cb) {
        impl_.subscribe(topic, std::move(cb), qos.wants_keep_latest());
        return std::make_shared<Subscription<RawBytes>>(topic);
    }

    const std::string& get_name() const { return impl_.node_id(); }
    commsys::Node& underlying() { return impl_; }  // escape hatch to the full commsys::Node API

    /// Public for symmetry with commsys::Node::start() (which this
    /// delegates to directly) -- make_node() below calls it for you
    /// in the common case, but it's not hidden if you construct a
    /// Node directly and want to control timing yourself.
    void start() { impl_.start(); }
    void spin_once(int budget_ms = 1) { impl_.spin_once(budget_ms); }

private:
    commsys::Node impl_;
};

using NodePtr = std::shared_ptr<Node>;

/// Constructs a Node and starts it, mirroring the common rclcpp
/// pattern of `auto node = std::make_shared<MyNode>(...)` followed
/// immediately by the node being ready to use -- commsys::Node
/// separates construction from start() (see API_GUIDE.md for why:
/// start() can throw, e.g. on a bind() failure, which is generally
/// considered better kept out of a constructor), so this helper does
/// both steps for callers who just want ROS-familiar ergonomics.
inline NodePtr make_node(std::string node_id, const NodeOptions& options = {}) {
    auto node = std::make_shared<Node>(std::move(node_id), options);
    node->start();
    return node;
}

/// Idempotent no-ops for API-surface familiarity with rclcpp::init()/
/// shutdown() -- commsys has no global runtime state that needs
/// initializing (no DDS participant, no middleware to bring up), so
/// there's nothing for these to actually do. Provided so code
/// structured the rclcpp way (init at startup, shutdown at exit)
/// doesn't need those two lines removed to port to/from this library.
inline void init(int argc = 0, char** argv = nullptr) { (void)argc; (void)argv; }
inline void shutdown() {}

/// Blocking spin, mirroring rclcpp::spin(node) -- processes callbacks
/// until `should_continue` returns false (defaults to "forever",
/// matching rclcpp::spin()'s usual behavior of running until the
/// process is killed; this library has no OS signal handling wired
/// in the way rclcpp does, so there is no automatic Ctrl+C exit --
/// pass an explicit predicate, e.g. tied to a signal handler you
/// install yourself, if you need one).
inline void spin(NodePtr node, std::function<bool()> should_continue = [] { return true; }) {
    while (should_continue()) node->spin_once(1);
}

/// Non-blocking single pass, mirroring rclcpp::spin_some(node) --
/// processes whatever's immediately available and returns.
inline void spin_some(NodePtr node) { node->spin_once(0); }

/// Not part of rclcpp's API, but provided since it's the practical
/// tool for writing testable code against this compatibility layer
/// (the same reasoning as commsys::Node::spin_for() itself).
inline void spin_for(NodePtr node, std::chrono::steady_clock::duration duration) {
    auto deadline = std::chrono::steady_clock::now() + duration;
    while (std::chrono::steady_clock::now() < deadline) node->spin_once(1);
}

}  // namespace ros_compat
}  // namespace commsys
