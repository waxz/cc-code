"""
transport.py
------------
Unified API over the two lower-level modules. The application talks
to `UnifiedTransport` and shouldn't need to know whether a given peer
is reached via shared memory (same host) or over a resilient network
channel (different host, e.g. over WiFi).

Routing rule: a peer registered with `local=True` gets a shared-memory
ring buffer pair; everything else gets a ResilientChannel. Each peer's
messages are serialized once via the shared Serializer, so switching a
peer between local and remote transport is a one-line config change.

Large-payload chunking (remote path only)
------------------------------------------
A single LaserScan message can be several KB -- larger than a typical
WiFi path's MTU (~1500B). Sending it as one UDP datagram means the OS
IP-fragments it, and IP fragmentation has a nasty property on a lossy
link: if *any one* fragment is dropped, the *entire* datagram is lost,
and nothing above the IP layer even finds out which piece was missing.
That turns a message that should need one retransmit into one that
silently vanishes.

So every remote-path message is wrapped with a small chunk header and,
if it's larger than MAX_CHUNK_BYTES, split into pieces before handing
each one to ResilientChannel (which already guarantees in-order
reliable delivery of each piece). The receiver reassembles by msg_id.
Small messages just become the chunk_count=1 case, so the header
format is uniform.
"""

import asyncio
import itertools
import struct
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional

from serialization import Serializer
from shared_memory_ipc import SPSCRingBuffer
from network_resilience import ResilientChannel, LinkState

# Conservative default: comfortably under a typical WiFi path's
# effective MTU (1500B Ethernet/WiFi frame minus IP/UDP headers,
# further reduced for any tunneling in between) so a chunk survives
# as a single, unfragmented IP packet.
MAX_CHUNK_BYTES = 1200
CHUNK_HEADER_FMT = "!IHH"  # msg_id(uint32), chunk_idx(uint16), chunk_count(uint16)
CHUNK_HEADER_SIZE = struct.calcsize(CHUNK_HEADER_FMT)

# Every payload (local or remote) carries a 1-byte format flag ahead of
# the data, so `_deliver` knows whether to run it through the generic
# Serializer or hand it to the app untouched. Pre-serialized formats
# like FlatBuffers must use FLAG_RAW -- running msgpack/pickle over an
# already-encoded FlatBuffers buffer would corrupt it, not decode it.
FLAG_SERIALIZED = 0
FLAG_RAW = 1


@dataclass
class PeerHandle:
    peer_id: str
    local: bool
    channel: object = None          # ResilientChannel, if remote
    tx_ring: SPSCRingBuffer = None  # outbound ring, if local
    rx_ring: SPSCRingBuffer = None  # inbound ring, if local
    reader_thread: threading.Thread = None
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _reassembly: dict = field(default_factory=dict)  # msg_id -> {idx: bytes}


class UnifiedTransport:
    def __init__(self, on_message: Callable[[str, object], None],
                 on_link_state: Optional[Callable[[str, LinkState], None]] = None,
                 use_msgpack: bool = True):
        self.serializer = Serializer(use_msgpack=use_msgpack)
        self.on_message = on_message
        self.on_link_state = on_link_state
        self.peers: dict[str, PeerHandle] = {}
        self._stop = threading.Event()
        self._msg_id_counter = itertools.count(1)

    # -- registration -----------------------------------------------------
    async def connect_remote(self, peer_id: str, local_addr, remote_addr):
        ch = ResilientChannel(
            local_addr=local_addr,
            remote_addr=remote_addr,
            on_message=lambda raw: self._handle_remote_raw(peer_id, raw),
            on_state_change=lambda state: self._link_state(peer_id, state),
        )
        await ch.start()
        self.peers[peer_id] = PeerHandle(peer_id=peer_id, local=False, channel=ch)

    def connect_local(self, peer_id: str, ring_name_tx: str, ring_name_rx: str,
                       capacity: int = 1 << 20, create: bool = True):
        tx_ring = SPSCRingBuffer(ring_name_tx, capacity=capacity, create=create)
        rx_ring = SPSCRingBuffer(ring_name_rx, capacity=capacity, create=create)
        handle = PeerHandle(peer_id=peer_id, local=True, tx_ring=tx_ring, rx_ring=rx_ring)
        self.peers[peer_id] = handle

        def _reader():
            while not self._stop.is_set():
                try:
                    raw = rx_ring.read(timeout=1.0)
                except TimeoutError:
                    continue
                if raw is None:
                    break
                self._deliver(peer_id, raw)

        t = threading.Thread(target=_reader, daemon=True)
        handle.reader_thread = t
        t.start()

    # -- send / receive ------------------------------------------------
    async def send(self, peer_id: str, message, reliable: bool = True):
        """Send an arbitrary Python object through the generic
        Serializer (msgpack/pickle)."""
        payload = self.serializer.dumps(message)
        await self._send_payload(peer_id, FLAG_SERIALIZED, payload, reliable)

    async def send_raw(self, peer_id: str, raw_bytes: bytes, reliable: bool = True):
        """Send an already-encoded payload (e.g. a FlatBuffers buffer
        built by flatbuffer_codec) without passing it through the
        generic Serializer. The receiver's on_message callback gets
        these bytes back untouched -- decode them with the matching
        flatbuffer_codec.read_*() function."""
        await self._send_payload(peer_id, FLAG_RAW, raw_bytes, reliable)

    async def _send_payload(self, peer_id: str, flag: int, payload: bytes, reliable: bool):
        handle = self.peers.get(peer_id)
        if handle is None:
            raise KeyError(f"unknown peer {peer_id}")
        framed = bytes([flag]) + payload
        if handle.local:
            handle.tx_ring.write(framed)
        else:
            await self._send_chunked(handle, framed, reliable)

    async def _send_chunked(self, handle: PeerHandle, payload: bytes, reliable: bool):
        chunks = [payload[i:i + MAX_CHUNK_BYTES]
                  for i in range(0, len(payload), MAX_CHUNK_BYTES)] or [b""]
        msg_id = next(self._msg_id_counter) & 0xFFFFFFFF
        # Hold the peer's send lock for the whole message: chunks rely
        # on ResilientChannel's own in-order delivery guarantee to
        # arrive un-interleaved with another message's chunks, which
        # only holds if we don't kick off a second chunked send on the
        # same channel before this one has been fully handed off.
        async with handle.send_lock:
            for idx, chunk in enumerate(chunks):
                header = struct.pack(CHUNK_HEADER_FMT, msg_id, idx, len(chunks))
                await handle.channel.send(header + chunk, reliable=reliable)

    def _handle_remote_raw(self, peer_id: str, raw: bytes):
        handle = self.peers[peer_id]
        msg_id, idx, count = struct.unpack(CHUNK_HEADER_FMT, raw[:CHUNK_HEADER_SIZE])
        chunk = raw[CHUNK_HEADER_SIZE:]
        if count == 1:
            self._deliver(peer_id, chunk)
            return
        parts = handle._reassembly.setdefault(msg_id, {})
        parts[idx] = chunk
        if len(parts) == count:
            complete = b"".join(parts[i] for i in range(count))
            del handle._reassembly[msg_id]
            self._deliver(peer_id, complete)

    def _deliver(self, peer_id: str, framed: bytes):
        flag, raw = framed[0], framed[1:]
        if flag == FLAG_RAW:
            message = raw
        else:
            message = self.serializer.loads(raw)
        self.on_message(peer_id, message)

    def _link_state(self, peer_id: str, state: LinkState):
        if self.on_link_state:
            self.on_link_state(peer_id, state)

    # -- teardown --------------------------------------------------------
    async def close(self):
        self._stop.set()
        for handle in self.peers.values():
            if handle.local:
                handle.tx_ring.mark_closed()
                handle.rx_ring.mark_closed()
                # The reader thread may be blocked inside rx_ring.read();
                # mark_closed() above lets it return None and exit on its
                # own. Join before releasing the buffer it points into,
                # or a wakeup racing the close() call segfaults/throws.
                if handle.reader_thread is not None:
                    handle.reader_thread.join(timeout=2.0)
                handle.tx_ring.close()
                handle.rx_ring.close()
            else:
                await handle.channel.close()
