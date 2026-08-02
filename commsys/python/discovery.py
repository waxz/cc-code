"""
discovery.py
-------------
Decentralized node discovery, in the spirit of ROS2/DDS: there is no
central "master" process (unlike ROS1's roscore). Any node can attach
to a well-known shared-memory table by name, claim a slot, and publish
what topics it produces/consumes. Every other node polls the same
table to build its own view of "who publishes/subscribes what, and
how do I reach them" -- entirely peer-to-peer.

This uses shared memory rather than UDP multicast (DDS's usual
mechanism) because it's guaranteed to work in any environment
(multicast is often blocked or misconfigured on real networks, and
unavailable in many sandboxes) and because it's a natural fit for the
common case of multiple nodes on one robot's onboard computer -- which
is also why real DDS implementations (e.g. iceoryx-backed ones) do the
same thing for same-host participants. Nodes on separate hosts would
need a different rendezvous mechanism (real multicast, or a known
seed-node list); that's a documented extension point, not implemented
here.

Liveness / resilience: each slot carries the owning PID. A node is
only considered active if BOTH its heartbeat is fresh (within `ttl`)
AND its process is still alive (`os.kill(pid, 0)`), so a node that
crashed without a clean unregister() is pruned quickly rather than
leaving a stale "ghost" publisher in every other node's routing table.
"""

import ctypes
import os
import time
from multiprocessing import shared_memory

REGISTRY_NAME = "/commsys_discovery"
CAPACITY = 64            # max simultaneous nodes
NODE_ID_LEN = 64
HOST_LEN = 64
TOPICS_LEN = 384         # "pub=imu,scan|sub=cmd_vel" style blob


class NodeSlot(ctypes.Structure):
    _fields_ = [
        ("active", ctypes.c_uint8),
        ("pid", ctypes.c_uint32),
        ("node_id", ctypes.c_char * NODE_ID_LEN),
        ("host", ctypes.c_char * HOST_LEN),
        ("port", ctypes.c_uint32),
        ("transport_pref", ctypes.c_uint8),  # 0=auto, 1=force shm, 2=force udp
        ("last_heartbeat_ns", ctypes.c_uint64),
        ("topics", ctypes.c_char * TOPICS_LEN),
    ]


class RegistryTable(ctypes.Structure):
    _fields_ = [("slots", NodeSlot * CAPACITY)]


class NodeInfo:
    __slots__ = ("node_id", "host", "port", "published", "subscribed", "pid", "transport_pref")

    def __init__(self, node_id, host, port, published, subscribed, pid, transport_pref=0):
        self.node_id = node_id
        self.host = host
        self.port = port
        self.published = published    # set[str]
        self.subscribed = subscribed  # set[str]
        self.pid = pid
        self.transport_pref = transport_pref  # 0=auto, 1=shm, 2=udp

    def __repr__(self):
        return (f"NodeInfo({self.node_id!r} @ {self.host}:{self.port}, "
                f"pub={sorted(self.published)}, sub={sorted(self.subscribed)})")


def _encode_topics(published, subscribed) -> bytes:
    blob = f"pub={','.join(published)}|sub={','.join(subscribed)}"
    encoded = blob.encode("utf-8")
    if len(encoded) >= TOPICS_LEN:
        raise ValueError("too many topics for fixed-size discovery slot; "
                          "increase TOPICS_LEN")
    return encoded


def _decode_topics(blob: bytes):
    text = blob.rstrip(b"\x00").decode("utf-8")
    pub_part, _, sub_part = text.partition("|")
    published = set(pub_part[4:].split(",")) if pub_part[4:] else set()
    subscribed = set(sub_part[4:].split(",")) if sub_part[4:] else set()
    return published, subscribed


def _pid_alive(pid: int) -> bool:
    if pid == 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return pid == os.getpid()  # PermissionError still means it exists
    except OSError:
        return False


class DiscoveryRegistry:
    """Attach (or create, if this is the first node up) the shared
    discovery table, and provide register/heartbeat/list_active.

    `lock`, if provided, must be a multiprocessing.Lock created by a
    common ancestor process and passed to every node (the same
    constraint MPMCQueue documents). Without it, register() has a real
    race: two processes claiming a slot at the same instant can both
    pick the same index and their field writes interleave, corrupting
    the record (e.g. one node's topics ending up under another node's
    id). For unrelated processes with no common ancestor, swap in a
    named POSIX semaphore -- the same production note as MPMCQueue.
    """

    def __init__(self, name: str = REGISTRY_NAME, capacity: int = CAPACITY, lock=None):
        assert capacity == CAPACITY, "capacity is fixed at import time for this reference impl"
        self.name = name
        self._lock = lock
        size = ctypes.sizeof(RegistryTable)
        try:
            self._shm = shared_memory.SharedMemory(name=name, create=True, size=size)
            self._table = RegistryTable.from_buffer(self._shm.buf)
            # No explicit zero-fill here: POSIX guarantees a freshly
            # ftruncate()-extended shared memory segment is already
            # zero-filled by the OS. An explicit memset() was tried
            # here originally and turned out to be actively harmful,
            # not just redundant -- it runs *after* the segment
            # becomes attachable to other processes, so a concurrent
            # attacher that writes a valid claim into a slot before
            # our memset reaches that slot has its write silently
            # erased. This was a real, reproducible corruption source
            # (a live node's discovery record getting clobbered by a
            # second node's registration racing the zero-fill).
        except FileExistsError:
            # Attach path. Python's own SharedMemory.__init__(create=True)
            # does shm_open() then ftruncate() as two separate, non-atomic
            # steps -- an attacher can see the segment exist (shm_open
            # succeeds) before the creator has resized it, and get
            # "ValueError: cannot mmap an empty file". This is a real,
            # observed race under concurrent process startup, not a
            # theoretical one; retry briefly rather than crash.
            deadline = time.monotonic() + 2.0
            while True:
                try:
                    self._shm = shared_memory.SharedMemory(name=name, create=False)
                    break
                except ValueError as e:
                    if "empty file" not in str(e) or time.monotonic() > deadline:
                        raise
                    time.sleep(0.002)
            from shared_memory_ipc import _unregister_from_resource_tracker
            _unregister_from_resource_tracker(self._shm)
            self._table = RegistryTable.from_buffer(self._shm.buf)
        self._my_slot = None

    def register(self, node_id: str, host: str, port: int, published, subscribed,
                 transport_pref: int = 0) -> int:
        """Claim a free slot (or a slot left behind by a dead process)
        for this node. Returns the slot index."""
        topics_blob = _encode_topics(published, subscribed)
        if self._lock is not None:
            with self._lock:
                return self._claim_slot(node_id, host, port, topics_blob, transport_pref)
        return self._claim_slot(node_id, host, port, topics_blob, transport_pref)

    def _claim_slot(self, node_id, host, port, topics_blob, transport_pref) -> int:
        for i in range(CAPACITY):
            slot = self._table.slots[i]
            if slot.active and _pid_alive(slot.pid) and slot.node_id != node_id.encode():
                continue
            slot.node_id = node_id.encode()
            slot.host = host.encode()
            slot.port = port
            slot.pid = os.getpid()
            slot.transport_pref = transport_pref
            slot.topics = topics_blob
            slot.last_heartbeat_ns = time.time_ns()
            slot.active = 1
            self._my_slot = i
            return i
        raise RuntimeError(f"discovery registry full (capacity={CAPACITY})")

    def heartbeat(self, slot_idx: int, published=None, subscribed=None):
        slot = self._table.slots[slot_idx]
        if published is not None or subscribed is not None:
            # topics can change at runtime (e.g. subscribe() called after start())
            pub = set(_decode_topics(slot.topics)[0]) if published is None else published
            sub = set(_decode_topics(slot.topics)[1]) if subscribed is None else subscribed
            slot.topics = _encode_topics(pub, sub)
        slot.last_heartbeat_ns = time.time_ns()

    def unregister(self, slot_idx: int):
        self._table.slots[slot_idx].active = 0

    def list_active(self, ttl_sec: float = 2.0, exclude_slot: int = None):
        now = time.time_ns()
        ttl_ns = int(ttl_sec * 1e9)
        result = []
        for i in range(CAPACITY):
            if i == exclude_slot:
                continue
            slot = self._table.slots[i]
            if not slot.active:
                continue
            if now - slot.last_heartbeat_ns > ttl_ns:
                continue
            if not _pid_alive(slot.pid):
                continue
            published, subscribed = _decode_topics(slot.topics)
            result.append(NodeInfo(
                node_id=slot.node_id.rstrip(b"\x00").decode(),
                host=slot.host.rstrip(b"\x00").decode(),
                port=slot.port,
                published=published,
                subscribed=subscribed,
                pid=slot.pid,
                transport_pref=slot.transport_pref,
            ))
        return result

    def close(self):
        self._table = None
        self._shm.close()

    def unlink(self):
        try:
            self._shm.unlink()
        except FileNotFoundError:
            pass
