"""
tests/test_network_resilience.py
----------------------------------
Unit tests for network_resilience.py. Uses real UDP sockets on
loopback (127.0.0.1) with a monkeypatched drop filter to simulate
WiFi-style loss, rather than mocking the transport -- exercises the
actual asyncio datagram path.
"""

import asyncio
import random
import sys
import os
import itertools

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from network_resilience import ResilientChannel, LinkState, _Protocol

_port_counter = itertools.count(20000)


def next_port_pair():
    return next(_port_counter), next(_port_counter)


def install_loss(channel: ResilientChannel, rate: float, seed: int = 0):
    """Patch a live channel's transport to drop incoming datagrams at
    `rate` probability, simulating a lossy WiFi link."""
    rng = random.Random(seed)
    proto = channel._transport._protocol
    original = _Protocol.datagram_received

    def lossy(self, data, addr):
        if rng.random() < rate:
            return
        original(self, data, addr)

    proto.datagram_received = lossy.__get__(proto, _Protocol)


async def make_pair(loss_rate=0.0, seed_a=1, seed_b=2, **kwargs):
    port_a, port_b = next_port_pair()
    a_received, b_received = [], []
    a = ResilientChannel(local_addr=("127.0.0.1", port_a),
                          remote_addr=("127.0.0.1", port_b),
                          on_message=a_received.append, **kwargs)
    b = ResilientChannel(local_addr=("127.0.0.1", port_b),
                          remote_addr=("127.0.0.1", port_a),
                          on_message=b_received.append, **kwargs)
    await a.start()
    await b.start()
    if loss_rate:
        install_loss(a, loss_rate, seed_a)
        install_loss(b, loss_rate, seed_b)
    return a, b, a_received, b_received


@pytest.mark.asyncio
async def test_basic_reliable_delivery():
    a, b, a_recv, b_recv = await make_pair()
    try:
        await a.send(b"hello", reliable=True)
        await asyncio.sleep(0.3)
        assert b_recv == [b"hello"]
    finally:
        await a.close()
        await b.close()


@pytest.mark.asyncio
async def test_unreliable_send_does_not_retransmit():
    a, b, a_recv, b_recv = await make_pair()
    try:
        # unreliable sends carry seq=0 always and are never buffered
        # for retransmit -- confirm one send produces at most one
        # delivery and no retry storm.
        await a.send(b"fire-and-forget", reliable=False)
        await asyncio.sleep(0.5)
        assert b_recv.count(b"fire-and-forget") == 1
        assert len(a._inflight) == 0
    finally:
        await a.close()
        await b.close()


@pytest.mark.asyncio
async def test_ordering_preserved_despite_reordered_arrival():
    """Force packets to be delivered to the app out of wire order by
    reordering them at the socket layer, and confirm the reorder
    buffer still hands them to the app in send order."""
    a, b, a_recv, b_recv = await make_pair()
    try:
        proto_b = b._transport._protocol
        held = []

        def reorder(self, data, addr):
            held.append((data, addr))
            if len(held) == 5:
                # release in reverse order
                for d, ad in reversed(held):
                    _Protocol.datagram_received(self, d, ad)

        proto_b.datagram_received = reorder.__get__(proto_b, _Protocol)

        for i in range(5):
            await a.send(f"m{i}".encode(), reliable=True)
        await asyncio.sleep(0.5)

        assert b_recv == [f"m{i}".encode() for i in range(5)]
    finally:
        await a.close()
        await b.close()


@pytest.mark.asyncio
async def test_duplicate_packet_delivered_once():
    a, b, a_recv, b_recv = await make_pair()
    try:
        proto_b = b._transport._protocol
        original = _Protocol.datagram_received

        def duplicate_first(self, data, addr):
            original(self, data, addr)
            original(self, data, addr)  # deliver the same datagram twice

        proto_b.datagram_received = duplicate_first.__get__(proto_b, _Protocol)

        await a.send(b"only-once", reliable=True)
        await asyncio.sleep(0.3)
        assert b_recv == [b"only-once"]
    finally:
        await a.close()
        await b.close()


@pytest.mark.asyncio
async def test_delivery_survives_sustained_loss():
    a, b, a_recv, b_recv = await make_pair(loss_rate=0.3, seed_a=11, seed_b=22)
    try:
        n = 60
        for i in range(n):
            await a.send(f"seq-{i}".encode(), reliable=True)
        # loop with generous timeout instead of a single fixed sleep,
        # since delivery time under loss varies
        deadline = asyncio.get_event_loop().time() + 12.0
        while len(b_recv) < n and asyncio.get_event_loop().time() < deadline:
            await asyncio.sleep(0.1)
        assert b_recv == [f"seq-{i}".encode() for i in range(n)]
    finally:
        await a.close()
        await b.close()


@pytest.mark.asyncio
async def test_link_state_degrades_under_high_loss():
    states = []
    port_a, port_b = next_port_pair()
    a = ResilientChannel(local_addr=("127.0.0.1", port_a),
                          remote_addr=("127.0.0.1", port_b),
                          on_state_change=states.append)
    b = ResilientChannel(local_addr=("127.0.0.1", port_b),
                          remote_addr=("127.0.0.1", port_a))
    await a.start()
    await b.start()
    install_loss(a, 0.6, seed=5)
    install_loss(b, 0.6, seed=6)
    try:
        for i in range(30):
            await a.send(f"x{i}".encode(), reliable=True)
        await asyncio.sleep(3.0)
        assert LinkState.DEGRADED in states or LinkState.DOWN in states
    finally:
        await a.close()
        await b.close()


@pytest.mark.asyncio
async def test_heartbeat_keeps_liveness_fresh_on_idle_channel():
    """With no data traffic at all, heartbeats alone should be enough
    to prevent the liveness timeout from firing a false reconnect."""
    reconnects = []
    port_a, port_b = next_port_pair()
    a = ResilientChannel(local_addr=("127.0.0.1", port_a),
                          remote_addr=("127.0.0.1", port_b),
                          heartbeat_interval=0.2, liveness_timeout=1.0,
                          on_reconnect=lambda: reconnects.append(1))
    b = ResilientChannel(local_addr=("127.0.0.1", port_b),
                          remote_addr=("127.0.0.1", port_a),
                          heartbeat_interval=0.2, liveness_timeout=1.0)
    await a.start()
    await b.start()
    try:
        await asyncio.sleep(2.5)  # several heartbeat intervals, no data sent
        assert reconnects == []
    finally:
        await a.close()
        await b.close()


@pytest.mark.asyncio
async def test_liveness_timeout_triggers_reconnect_hook_when_peer_silent():
    reconnects = []
    port_a, port_b = next_port_pair()
    a = ResilientChannel(local_addr=("127.0.0.1", port_a),
                          remote_addr=("127.0.0.1", port_b),
                          heartbeat_interval=0.2, liveness_timeout=0.5,
                          on_reconnect=lambda: reconnects.append(1))
    await a.start()
    # no peer 'b' ever started -- a never hears anything back
    try:
        await asyncio.sleep(2.0)
        assert len(reconnects) >= 1
    finally:
        await a.close()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
