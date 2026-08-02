"""tests/test_transport.py"""
import asyncio
import sys
import os
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from transport import UnifiedTransport


def unique_name():
    return uuid.uuid4().hex[:12]


@pytest.mark.asyncio
async def test_local_peer_send_receive_roundtrip():
    received = []
    t = UnifiedTransport(on_message=lambda peer, msg: received.append((peer, msg)))
    tx = f"tx_{unique_name()}"
    rx = f"rx_{unique_name()}"
    t.connect_local("me", ring_name_tx=tx, ring_name_rx=rx, capacity=1 << 16)
    try:
        # A peer talking to itself: write to tx, and since the reader
        # thread reads rx, manually mirror this test by reading tx
        # directly to confirm data actually landed in shared memory
        # (the more realistic loopback exercise is example_demo.py).
        await t.send("me", {"hello": "world"})
        handle = t.peers["me"]
        raw = handle.tx_ring.read(timeout=1.0)
        assert raw is not None
        assert t.serializer.loads(raw[1:]) == {"hello": "world"}  # [0] is the format flag
    finally:
        await t.close()


@pytest.mark.asyncio
async def test_remote_peer_send_receive_roundtrip():
    received_a, received_b = [], []
    a = UnifiedTransport(on_message=lambda peer, msg: received_a.append((peer, msg)))
    b = UnifiedTransport(on_message=lambda peer, msg: received_b.append((peer, msg)))
    await a.connect_remote("b", local_addr=("127.0.0.1", 21001), remote_addr=("127.0.0.1", 21002))
    await b.connect_remote("a", local_addr=("127.0.0.1", 21002), remote_addr=("127.0.0.1", 21001))
    try:
        await a.send("b", {"type": "ping", "n": 1})
        await asyncio.sleep(0.3)
        assert received_b == [("a", {"type": "ping", "n": 1})]
    finally:
        await a.close()
        await b.close()


@pytest.mark.asyncio
async def test_unknown_peer_raises():
    t = UnifiedTransport(on_message=lambda peer, msg: None)
    with pytest.raises(KeyError):
        await t.send("nonexistent", {"a": 1})
    await t.close()


@pytest.mark.asyncio
async def test_large_payload_is_chunked_and_reassembled():
    """A LaserScan-sized message (bigger than MAX_CHUNK_BYTES) must
    arrive whole and byte-identical on the other side, confirming the
    chunk/reassembly path works end to end."""
    import numpy as np
    from flatbuffer_codec import build_laser_scan

    received_b = []
    a = UnifiedTransport(on_message=lambda peer, msg: None)
    b = UnifiedTransport(on_message=lambda peer, msg: received_b.append(msg))
    await a.connect_remote("b", local_addr=("127.0.0.1", 21011), remote_addr=("127.0.0.1", 21012))
    await b.connect_remote("a", local_addr=("127.0.0.1", 21012), remote_addr=("127.0.0.1", 21011))
    try:
        ranges = np.random.uniform(0.1, 25.0, size=2000).astype(np.float32)
        scan_bytes = build_laser_scan(1, -3.14, 3.14, 0.003, 0.1, 30.0, ranges)
        assert len(scan_bytes) > 1200  # confirm this actually exercises chunking

        # Send raw flatbuffer bytes via the public raw-passthrough API
        # (FlatBuffers messages are pre-serialized, so they bypass the
        # generic Serializer).
        await a.send_raw("b", scan_bytes, reliable=True)
        await asyncio.sleep(0.5)

        assert len(received_b) == 1
        assert received_b[0] == scan_bytes
    finally:
        await a.close()
        await b.close()


@pytest.mark.asyncio
async def test_large_payload_survives_loss_during_chunk_transfer():
    from network_resilience import ResilientChannel, _Protocol
    import random

    a = UnifiedTransport(on_message=lambda peer, msg: None)
    received_b = []
    b = UnifiedTransport(on_message=lambda peer, msg: received_b.append(msg))
    await a.connect_remote("b", local_addr=("127.0.0.1", 21021), remote_addr=("127.0.0.1", 21022))
    await b.connect_remote("a", local_addr=("127.0.0.1", 21022), remote_addr=("127.0.0.1", 21021))

    rng = random.Random(7)
    for peer_id, t in (("b", a), ("a", b)):
        proto = t.peers[peer_id].channel._transport._protocol
        original = _Protocol.datagram_received

        def lossy(self, data, addr, _orig=original):
            if rng.random() < 0.25:
                return
            _orig(self, data, addr)
        proto.datagram_received = lossy.__get__(proto, _Protocol)

    try:
        payload = bytes(range(256)) * 20  # 5120 bytes -> multiple chunks
        await a.send_raw("b", payload, reliable=True)

        deadline = asyncio.get_event_loop().time() + 10.0
        while not received_b and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.1)

        assert len(received_b) == 1
        assert received_b[0] == payload
    finally:
        await a.close()
        await b.close()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
