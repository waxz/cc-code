"""
node.py
--------
A ROS-like Node: advertise(topic), publish(topic, payload),
subscribe(topic, callback). Peers are found via discovery.py --
there's no need to know a subscriber's address ahead of time, the way
you'd need to with UnifiedTransport's connect_local/connect_remote.
Every node polls the shared discovery table, and when it sees a peer
that publishes something it subscribes to (or vice versa), it wires up
a data link automatically.

Two link types, chosen automatically per peer pair:

  - Same host -> a dedicated SPSC shared-memory ring per (publisher,
    subscriber) pair, named deterministically so both sides can find
    it without further coordination. The publisher always creates it;
    the subscriber attaches with a short retry loop. This is the
    "multiple nodes on one robot computer" case and is effectively
    zero-copy, matching what real DDS implementations do for same-
    host participants.

  - Different host -> best-effort UDP, matching ROS2's default QoS for
    high-rate sensor topics (IMU, LaserScan): no ACKs, no
    retransmission, lowest latency, and a dropped sample just means
    the next one arrives on schedule. A topic that needs guaranteed
    delivery could instead be routed through network_resilience.py's
    ResilientChannel -- that wiring is a natural extension, not
    implemented here since none of the demo topics need it.

Wire envelope (both link types): topic name, sequence number, and a
send-side wall-clock timestamp precede the payload, so a subscriber
can measure one-way latency and detect drops via sequence gaps without
needing anything payload-specific.
"""

import asyncio
import itertools
import os
import socket
import struct
import time
from dataclasses import dataclass, field

from discovery import DiscoveryRegistry
import discovery
from shared_memory_ipc import SPSCRingBuffer, LatestValueSlot

ENVELOPE_FMT = "!H I Q H"  # topic_len(uint16), seq(uint32), send_ns(uint64), sender_len(uint16)
ENVELOPE_HDR = struct.calcsize(ENVELOPE_FMT)
DISCOVERY_POLL_INTERVAL = 0.15
HEARTBEAT_INTERVAL = 0.5
DISCOVERY_TTL = 2.0

# UDP has no framing of its own beyond one packet == one send() call, and
# a raw datagram over ~65507B either fails outright (as it does with
# asyncio's fire-and-forget sendto(), which does *not* raise on this --
# it just silently fails at the OS level, so the caller never even
# finds out) or, on a real network with a ~1500B MTU, gets IP-fragmented
# such that losing any *one* fragment loses the whole datagram. Every
# UDP publish is therefore chunked below this size and reassembled on
# the receive side, the same defensive move transport.py makes for its
# network path.
MAX_UDP_CHUNK = 1200
CHUNK_HDR_FMT = "!IHH"  # msg_id(uint32), chunk_idx(uint16), chunk_count(uint16)
CHUNK_HDR_SIZE = struct.calcsize(CHUNK_HDR_FMT)


def _pack_envelope(topic: str, seq: int, send_ns: int, sender_id: str, payload: bytes) -> bytes:
    topic_b = topic.encode()
    sender_b = sender_id.encode()
    header = struct.pack(ENVELOPE_FMT, len(topic_b), seq, send_ns, len(sender_b))
    # b''.join() computes the total size once and copies each piece in a
    # single pass. Chained `+` (header + topic_b + sender_b + payload)
    # instead builds up intermediate buffers, and the *last* `+` copies
    # the entire payload again into a new combined buffer -- an extra
    # full-payload-sized memcpy on every publish that's pure waste for
    # anything beyond a few dozen bytes.
    return b"".join((header, topic_b, sender_b, payload))


def _unpack_envelope(raw: bytes):
    topic_len, seq, send_ns, sender_len = struct.unpack_from(ENVELOPE_FMT, raw, 0)
    off = ENVELOPE_HDR
    topic = raw[off:off + topic_len].decode()
    off += topic_len
    sender_id = raw[off:off + sender_len].decode()
    off += sender_len
    payload = raw[off:]
    return topic, seq, send_ns, sender_id, payload


def _link_ring_name(publisher_id: str, subscriber_id: str) -> str:
    return f"/commsys_link_{publisher_id}_{subscriber_id}"


def _link_slot_name(publisher_id: str, subscriber_id: str) -> str:
    return f"/commsys_slot_{publisher_id}_{subscriber_id}"


LATEST_PREFIX = "~"  # marks a subscribed topic as wanting keep_latest semantics


def _strip_latest(topics: set) -> set:
    return {t.lstrip(LATEST_PREFIX) for t in topics}


def _latest_only(topics: set) -> set:
    return {t.lstrip(LATEST_PREFIX) for t in topics if t.startswith(LATEST_PREFIX)}


@dataclass
class _SubStats:
    count: int = 0
    drops: int = 0
    bytes_total: int = 0
    latencies_ns: list = field(default_factory=list)
    _last_seq_by_sender: dict = field(default_factory=dict)  # sender_id -> last seq seen


class _UdpProtocol(asyncio.DatagramProtocol):
    def __init__(self, on_datagram):
        self._on_datagram = on_datagram

    def datagram_received(self, data, addr):
        self._on_datagram(data, addr)


class Node:
    def __init__(self, node_id: str, host: str = "127.0.0.1",
                 udp_port: int = 0, force_transport: str = None,
                 registry_name: str = None, discovery_lock=None,
                 shm_ring_capacity: int = 16 << 20,
                 shm_slot_capacity: int = 1 << 20):
        """force_transport: None for automatic (shm if same host, else
        udp), or "udp"/"shm" to force a link type regardless of host
        -- useful for demos/tests that want to exercise the network
        path even when actually running on one machine.
        registry_name: override the discovery table's shared-memory
        name (default: discovery.REGISTRY_NAME) -- mainly for test
        isolation, so concurrent test runs don't see each other's
        nodes.
        discovery_lock: a multiprocessing.Lock shared by every node in
        the process tree, protecting discovery's slot-claim race (see
        discovery.DiscoveryRegistry). Required for correctness whenever
        multiple nodes might call start() around the same instant, as
        in a multi-process launch -- with no lock, two nodes claiming a
        slot simultaneously can corrupt each other's discovery record.
        shm_ring_capacity: bytes reserved per same-host publisher link
        (default 16MB). Too small relative to your payload size means
        the ring holds only a message or two, so the publisher spends
        most of its time backoff-spinning waiting for the subscriber
        to drain rather than actually writing -- size this to comfortably
        outrun a burst of your largest topic (e.g. several point clouds'
        worth), not just fit one message."""
        self.node_id = node_id
        self.host = host
        self.force_transport = force_transport
        self._udp_port_requested = udp_port
        self._shm_ring_capacity = shm_ring_capacity
        self._shm_slot_capacity = shm_slot_capacity
        self._registry = DiscoveryRegistry(name=registry_name or discovery.REGISTRY_NAME,
                                            lock=discovery_lock)
        self._slot = None
        self._published: set[str] = set()
        self._subscribed: dict[str, callable] = {}
        self._udp_transport = None
        self._udp_socket = None
        self._known_peers: dict[str, object] = {}   # node_id -> NodeInfo, last seen
        self._out_rings: dict[str, SPSCRingBuffer] = {}   # subscriber_node_id -> ring (FIFO topics)
        self._in_rings: dict[str, tuple] = {}             # publisher_node_id -> (ring, poll_task)
        self._out_slots: dict[str, LatestValueSlot] = {}  # subscriber_node_id -> slot (keep_latest topics)
        self._in_slots: dict[str, tuple] = {}             # publisher_node_id -> (slot, poll_task)
        self._peer_latest_topics: dict[str, set] = {}     # peer_id -> topics that peer wants keep_latest
        self._keep_latest_topics: set = set()             # topics *I* subscribe to with keep_latest=True
        self._seq_by_topic: dict[str, int] = {}
        self.stats: dict[str, _SubStats] = {}
        self._tasks = []
        self._stopped = False
        self._udp_msg_id_counter = itertools.count(1)
        self._udp_reassembly: dict[tuple, dict] = {}  # (addr, msg_id) -> {idx: bytes}

    async def start(self):
        loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # The OS default UDP buffer (~208KB on Linux) is easily
        # overflowed by a bursty publisher, especially now that large
        # payloads are split into many small chunks -- a message needs
        # *all* of its chunks to reassemble, so buffer overflow under a
        # chunked stream is worse than under single-datagram traffic of
        # the same size (losing any one chunk loses the whole message).
        # Request more headroom; best-effort if the OS caps it lower.
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8 << 20)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8 << 20)
        except OSError:
            pass
        sock.bind((self.host, self._udp_port_requested))
        sock.setblocking(False)
        self._udp_socket = sock
        self._udp_transport, _ = await loop.create_datagram_endpoint(
            lambda: _UdpProtocol(self._on_udp_datagram), sock=sock)
        self.udp_port = sock.getsockname()[1]

        self._slot = self._registry.register(
            self.node_id, self.host, self.udp_port, self._published,
            self._discovery_visible_subscribed(),
            transport_pref=self._transport_pref_code())
        self._tasks.append(asyncio.create_task(self._heartbeat_loop()))
        self._tasks.append(asyncio.create_task(self._discovery_loop()))

    def advertise(self, topic: str):
        self._published.add(topic)
        self._seq_by_topic.setdefault(topic, 0)

    def subscribe(self, topic: str, callback, keep_latest: bool = False):
        """keep_latest=True: use a lock-free single-slot 'latest value
        wins' link instead of the default FIFO ring for this topic.
        The writer never blocks or queues; a slow reader always gets
        the freshest sample instead of working through a backlog, at
        the cost of possibly missing intermediate values. This is the
        right choice for a live sensor feed driving a control loop
        (IMU, pose) where bounded staleness matters more than not
        missing any single sample -- see shared_memory_ipc.LatestValueSlot.
        Default (False) is FIFO: every message delivered, in order,
        with no bound on how far behind a slow subscriber can fall."""
        self._subscribed[topic] = callback
        self.stats[topic] = _SubStats()
        if keep_latest:
            self._keep_latest_topics.add(topic)

    def _discovery_visible_subscribed(self) -> set:
        return {f"{LATEST_PREFIX}{t}" if t in self._keep_latest_topics else t
                for t in self._subscribed}

    async def publish(self, topic: str, payload: bytes):
        if topic not in self._published:
            raise ValueError(f"{self.node_id}: publish to un-advertised topic {topic!r}")
        seq = self._seq_by_topic[topic]
        self._seq_by_topic[topic] = seq + 1
        send_ns = time.time_ns()
        envelope = _pack_envelope(topic, seq, send_ns, self.node_id, payload)

        for peer_id, (kind, target) in list(self._known_peers.items()):
            if topic not in target.subscribed:
                continue
            if kind == "shm":
                if topic in self._peer_latest_topics.get(peer_id, ()):
                    slot = self._out_slots.get(peer_id)
                    if slot is not None:
                        slot.write(envelope)  # never blocks, regardless of reader
                        # write() itself has no internal await point
                        # (unlike the ring's backoff loop), so without
                        # an explicit yield here, a tight unpaced
                        # publish loop targeting a keep_latest topic
                        # would never give the event loop a turn at
                        # all -- starving the subscriber's poll task
                        # (and everything else on this loop) for as
                        # long as the publish loop keeps running.
                        await asyncio.sleep(0)
                else:
                    ring = self._out_rings.get(peer_id)
                    if ring is not None:
                        await self._async_ring_write(ring, envelope, timeout=0.05)
            elif kind == "udp":
                self._send_udp_chunked(envelope, (target.host, target.port))

    @staticmethod
    async def _async_ring_write(ring: SPSCRingBuffer, envelope: bytes, timeout: float) -> bool:
        # SPSCRingBuffer.write()'s backoff uses time.sleep(), a real
        # blocking call. Calling it from inside a coroutine doesn't just
        # block the current task -- since asyncio is single-threaded, it
        # blocks the *entire event loop*, so nothing else on this loop
        # (the reader task included) can run until the ring frees up
        # space on its own. That's a real deadlock-shaped starvation
        # pattern under load: the publisher can't proceed because the
        # ring is full, and the ring can't drain because the reader task
        # never gets scheduled while the publisher is blocked. Polling
        # with try_write() + asyncio.sleep() instead keeps every backoff
        # tick a real yield point, so the reader gets to run between
        # attempts.
        deadline = time.monotonic() + timeout
        spins = 0
        while not ring.try_write(envelope):
            if time.monotonic() > deadline:
                return False  # slow subscriber: drop rather than block the publisher
            spins += 1
            await asyncio.sleep(0 if spins < 200 else 0.0005)
        return True

    def _send_udp_chunked(self, envelope: bytes, addr):
        chunks = [envelope[i:i + MAX_UDP_CHUNK]
                  for i in range(0, len(envelope), MAX_UDP_CHUNK)] or [b""]
        msg_id = next(self._udp_msg_id_counter) & 0xFFFFFFFF
        for idx, chunk in enumerate(chunks):
            header = struct.pack(CHUNK_HDR_FMT, msg_id, idx, len(chunks))
            self._udp_transport.sendto(header + chunk, addr)

    # -- peer discovery / link setup -----------------------------------
    async def _discovery_loop(self):
        try:
            while not self._stopped:
                peers = self._registry.list_active(ttl_sec=DISCOVERY_TTL, exclude_slot=self._slot)
                seen_ids = set()
                for peer in peers:
                    seen_ids.add(peer.node_id)
                    peer_latest = _latest_only(peer.subscribed)
                    peer.subscribed = _strip_latest(peer.subscribed)  # normalize for all downstream matching
                    relevant = (bool(self._published & peer.subscribed) or
                                bool(peer.published & self._subscribed.keys()))
                    if not relevant:
                        continue
                    self._peer_latest_topics[peer.node_id] = peer_latest
                    # Always reconcile, not just on first discovery:
                    # _setup_link only creates a link if the relevant
                    # dict doesn't already have one for this peer, so
                    # repeated calls are a no-op once set up (it also
                    # refreshes _known_peers[peer.node_id] with the
                    # current peer info every time, which is what keeps
                    # topic-set changes visible to publish()'s routing).
                    # This matters because a peer's topic set can
                    # genuinely change after its first registration
                    # (e.g. subscribe() called shortly after start(), so
                    # the first discovery sees an empty topic set and
                    # only a later heartbeat carries the real one) --
                    # without reconciling on every scan, that link would
                    # never get created at all.
                    self._setup_link(peer)
                # drop peers that vanished
                for gone in set(self._known_peers) - seen_ids:
                    self._teardown_link(gone)
                await asyncio.sleep(DISCOVERY_POLL_INTERVAL)
        except asyncio.CancelledError:
            pass

    def _transport_pref_code(self) -> int:
        return {"shm": 1, "udp": 2}.get(self.force_transport, 0)

    def _use_shm(self, peer) -> bool:
        # Symmetric rule -- both sides must independently reach the same
        # answer without further coordination, since neither side asks
        # the other "what did you decide?". UDP always works, so any
        # UDP preference (mine or theirs) wins; shared memory is only
        # chosen when BOTH sides allow it and the hosts actually match.
        my_pref = self._transport_pref_code()
        if my_pref == 2 or peer.transport_pref == 2:
            return False
        if peer.host != self.host:
            return False
        return True

    def _setup_link(self, peer):
        kind = "shm" if self._use_shm(peer) else "udp"
        self._known_peers[peer.node_id] = (kind, peer)
        if kind != "shm":
            return
        peer_latest = self._peer_latest_topics.get(peer.node_id, set())

        # I publish something they subscribe to -> I own (create) the
        # right kind of link, or both if this peer wants a mix.
        shared_out = self._published & peer.subscribed
        if shared_out - peer_latest and peer.node_id not in self._out_rings:
            name = _link_ring_name(self.node_id, peer.node_id)
            self._out_rings[peer.node_id] = SPSCRingBuffer(
                name, capacity=self._shm_ring_capacity, create=True)
        if shared_out & peer_latest and peer.node_id not in self._out_slots:
            name = _link_slot_name(self.node_id, peer.node_id)
            self._out_slots[peer.node_id] = LatestValueSlot(
                name, capacity=self._shm_slot_capacity, create=True)

        # they publish something I subscribe to -> attach to whichever
        # link type *I* declared for those topics (both sides agree
        # since this is driven by my own subscribe(keep_latest=...)
        # choice, communicated to them via the ~ prefix).
        shared_in = peer.published & self._subscribed.keys()
        if shared_in - self._keep_latest_topics and peer.node_id not in self._in_rings:
            name = _link_ring_name(peer.node_id, self.node_id)
            self._tasks.append(asyncio.create_task(self._attach_in_ring(peer.node_id, name)))
        if shared_in & self._keep_latest_topics and peer.node_id not in self._in_slots:
            name = _link_slot_name(peer.node_id, self.node_id)
            self._tasks.append(asyncio.create_task(self._attach_in_slot(peer.node_id, name)))

    async def _attach_in_ring(self, publisher_id: str, name: str):
        ring = None
        for _ in range(40):  # ~2s of retries for the publisher to create it
            try:
                ring = SPSCRingBuffer(name, create=False)
                break
            except FileNotFoundError:
                await asyncio.sleep(0.05)
        if ring is None:
            return
        task = asyncio.create_task(self._poll_ring(ring))
        self._in_rings[publisher_id] = (ring, task)
        self._tasks.append(task)

    async def _poll_ring(self, ring: SPSCRingBuffer):
        # Cooperative, event-loop-native polling instead of a blocking
        # OS thread + call_soon_threadsafe. The thread-based version had
        # a real, measured problem: nothing guarantees the OS scheduler
        # gives a separate reader thread timely CPU time relative to the
        # main event-loop thread. On this sandbox's single core, a
        # CPU-bound publisher starved the reader thread for ~2.5 seconds
        # before it ran even once -- every message published during that
        # window was stuck with multi-hundred-millisecond latency by the
        # time it was finally dispatched, even though nothing was
        # actually wrong with the ring buffer itself.
        #
        # An asyncio task has no such gap: it shares the same event
        # loop's cooperative task queue as the publisher, so it gets a
        # turn every time the loop cycles, regardless of what the OS
        # scheduler is doing with threads. Draining is prioritized (loop
        # right through a full backlog with no sleep at all) so a burst
        # gets flushed in one scheduling turn instead of one message at
        # a time with a sleep in between.
        spins = 0
        while not self._stopped:
            raw = ring.try_read()
            if raw is not None:
                self._dispatch(raw)
                spins = 0
                continue  # more may be queued; drain before yielding
            if ring.is_closed:
                return
            spins += 1
            # Empty ring: yield to the event loop (lets the publisher
            # and other tasks run) with a backoff that stays tight
            # under light idling and only backs off once it's clear
            # nothing is coming soon.
            if spins < 200:
                await asyncio.sleep(0)
            else:
                await asyncio.sleep(0.001)

    async def _attach_in_slot(self, publisher_id: str, name: str):
        slot = None
        for _ in range(40):  # ~2s of retries for the publisher to create it
            try:
                slot = LatestValueSlot(name, create=False)
                break
            except FileNotFoundError:
                await asyncio.sleep(0.05)
        if slot is None:
            return
        task = asyncio.create_task(self._poll_slot(slot))
        self._in_slots[publisher_id] = (slot, task)
        self._tasks.append(task)

    async def _poll_slot(self, slot: LatestValueSlot):
        # Unlike _poll_ring, there's no backlog to drain here by
        # design -- try_read() always returns whatever the latest
        # write was, or None. The polling interval directly *is* the
        # bounded, predictable staleness this primitive promises: a
        # steady 1ms poll means a subscriber is never more than
        # ~1ms-plus-network/queue-time behind the freshest publish,
        # regardless of how far ahead the publisher has otherwise
        # raced -- there's no queue depth for that gap to hide in.
        last_seen = None
        while not self._stopped:
            val = slot.try_read()
            if val is not None and val is not last_seen and val != last_seen:
                last_seen = val
                self._dispatch(val)
            if slot.is_closed:
                return
            await asyncio.sleep(0.001)

    def _teardown_link(self, peer_id: str):
        self._known_peers.pop(peer_id, None)
        ring = self._out_rings.pop(peer_id, None)
        if ring is not None:
            ring.mark_closed()
            ring.close()
            ring.unlink()
        slot = self._out_slots.pop(peer_id, None)
        if slot is not None:
            slot.mark_closed()
            slot.close()
            slot.unlink()
        entry = self._in_slots.pop(peer_id, None)
        if entry is not None:
            slot, task = entry
            task.cancel()
            slot.mark_closed()
            slot.close()
        entry = self._in_rings.pop(peer_id, None)
        if entry is not None:
            ring, task = entry
            task.cancel()
            ring.mark_closed()
            ring.close()

    # -- receive path ----------------------------------------------------
    def _on_udp_datagram(self, data: bytes, addr):
        msg_id, idx, count = struct.unpack_from(CHUNK_HDR_FMT, data, 0)
        chunk = data[CHUNK_HDR_SIZE:]
        if count == 1:
            self._dispatch(chunk)
            return
        key = (addr, msg_id)
        parts = self._udp_reassembly.setdefault(key, {})
        parts[idx] = chunk
        if len(parts) == count:
            complete = b"".join(parts[i] for i in range(count))
            del self._udp_reassembly[key]
            self._dispatch(complete)

    def _dispatch(self, raw: bytes):
        recv_ns = time.time_ns()
        topic, seq, send_ns, sender_id, payload = _unpack_envelope(raw)
        callback = self._subscribed.get(topic)
        if callback is None:
            return
        st = self.stats[topic]
        st.count += 1
        st.bytes_total += len(payload)
        st.latencies_ns.append(recv_ns - send_ns)
        last_seq = st._last_seq_by_sender.get(sender_id, -1)
        if last_seq >= 0 and seq != last_seq + 1:
            st.drops += max(0, seq - last_seq - 1)
        st._last_seq_by_sender[sender_id] = seq
        callback(payload)

    async def _heartbeat_loop(self):
        try:
            while not self._stopped:
                self._registry.heartbeat(self._slot, published=self._published,
                                          subscribed=self._discovery_visible_subscribed())
                await asyncio.sleep(HEARTBEAT_INTERVAL)
        except asyncio.CancelledError:
            pass

    async def stop(self):
        self._stopped = True
        for t in self._tasks:
            t.cancel()
        for peer_id in list(self._known_peers):
            self._teardown_link(peer_id)
        if self._udp_transport:
            self._udp_transport.close()
        if self._slot is not None:
            self._registry.unregister(self._slot)
        self._registry.close()
