"""
network_resilience.py
----------------------
Reliable messaging over an UNRELIABLE transport (UDP), designed for
links like WiFi where you get packet loss, jitter, brief blackouts,
and occasional full drops/roaming events -- but where TCP's strict
in-order head-of-line blocking is often the wrong tradeoff.

Mechanisms implemented:
  - Sequence numbers + cumulative/selective ACKs
  - Adaptive retransmit timeout (Jacobson/Karels, same idea as TCP)
  - Exponential backoff on repeated loss
  - Sliding window flow control (bounded in-flight messages)
  - Heartbeat / keepalive with liveness timeout -> triggers reconnect
  - Reorder buffer for in-order delivery to the application
  - Link quality state machine (HEALTHY / DEGRADED / DOWN) so the
    application (or the unified transport) can react -- e.g. shed
    non-critical traffic, or fail over.
  - Automatic reconnect with exponential backoff + jitter, and an
    on_reconnect hook for state resync after a blackout.

This is a compact reference implementation, not a replacement for a
hardened protocol (QUIC / KCP / ENet) in a production system carrying
real user traffic -- see README for that tradeoff discussion.
"""

import asyncio
import struct
import time
import random
import logging
from enum import Enum
from collections import deque

logger = logging.getLogger("resilient_channel")

PKT_DATA = 1
PKT_ACK = 2
PKT_HEARTBEAT = 3
PKT_HEARTBEAT_ACK = 4

# type(1) | seq(4) | flags(1)
HEADER_FMT = "!BIB"
HEADER_SIZE = struct.calcsize(HEADER_FMT)

FLAG_RELIABLE = 0x1


class LinkState(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


class RTTEstimator:
    """Adaptive RTO, same technique TCP uses (RFC 6298 style), so the
    retransmit timer tightens on a clean link and loosens automatically
    when WiFi gets jittery, instead of using one fixed timeout."""

    def __init__(self):
        self.srtt = None
        self.rttvar = None
        self.rto = 0.3
        # Separate multiplicative backoff layer on top of the base RTO
        # estimate. A burst of correlated timeouts (e.g. a whole send
        # window lost together) should make us back off, but a single
        # successful ack proves the link is still alive, so we snap the
        # multiplier back down immediately rather than requiring it to
        # decay away one halving at a time -- that's what previously let
        # the timer get stuck pinned at its ceiling for many seconds
        # after the link had already recovered.
        self.backoff_mult = 1.0

    def update(self, sample: float):
        if self.srtt is None:
            self.srtt = sample
            self.rttvar = sample / 2
        else:
            alpha, beta = 0.125, 0.25
            self.rttvar = (1 - beta) * self.rttvar + beta * abs(self.srtt - sample)
            self.srtt = (1 - alpha) * self.srtt + alpha * sample
        self.rto = max(0.05, min(5.0, self.srtt + 4 * self.rttvar))

    def backoff(self):
        self.backoff_mult = min(self.backoff_mult * 1.5, 16.0)

    def on_ack_received(self):
        self.backoff_mult = 1.0

    @property
    def effective_rto(self) -> float:
        return min(self.rto * self.backoff_mult, 8.0)


class _Protocol(asyncio.DatagramProtocol):
    def __init__(self, on_packet):
        self._on_packet = on_packet
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        self._on_packet(data, addr)

    def error_received(self, exc):
        logger.warning("udp error: %s", exc)


class ResilientChannel:
    """
    One logical connection to a remote peer over UDP.

    Usage:
        ch = ResilientChannel(local_addr=("0.0.0.0", 9000),
                               remote_addr=("192.168.1.42", 9000),
                               on_message=handle_msg,
                               on_state_change=handle_state)
        await ch.start()
        await ch.send(b"hello", reliable=True)
    """

    def __init__(self, local_addr, remote_addr=None, on_message=None,
                 on_state_change=None, on_reconnect=None,
                 window_size: int = 64, heartbeat_interval: float = 1.0,
                 liveness_timeout: float = 5.0):
        self.local_addr = local_addr
        self.remote_addr = remote_addr
        self.on_message = on_message
        self.on_state_change = on_state_change
        self.on_reconnect = on_reconnect
        self.window_size = window_size
        self.heartbeat_interval = heartbeat_interval
        self.liveness_timeout = liveness_timeout

        self._transport = None
        self._protocol = None
        self._send_seq = 0
        self._recv_expected = 0
        self._reorder_buf = {}
        self._inflight = {}          # seq -> (payload, sent_time, tries)
        self._inflight_order = deque()
        self._rtt = RTTEstimator()
        self._last_recv_time = time.monotonic()
        self._state = LinkState.HEALTHY
        self._recent_losses = deque(maxlen=20)   # 1 = loss, 0 = ok
        self._window_sem = asyncio.Semaphore(window_size)
        self._tasks = []
        self._closed = False

    # -- lifecycle -------------------------------------------------------
    async def start(self):
        loop = asyncio.get_running_loop()
        self._transport, self._protocol = await loop.create_datagram_endpoint(
            lambda: _Protocol(self._handle_packet),
            local_addr=self.local_addr,
        )
        self._tasks.append(asyncio.create_task(self._retransmit_loop()))
        self._tasks.append(asyncio.create_task(self._heartbeat_loop()))
        self._tasks.append(asyncio.create_task(self._liveness_loop()))
        logger.info("channel started on %s", self.local_addr)

    async def close(self):
        self._closed = True
        for t in self._tasks:
            t.cancel()
        if self._transport:
            self._transport.close()

    # -- sending -----------------------------------------------------------
    async def send(self, payload: bytes, reliable: bool = True):
        if reliable:
            await self._window_sem.acquire()
            seq = self._send_seq
            self._send_seq += 1
            flags = FLAG_RELIABLE
            header = struct.pack(HEADER_FMT, PKT_DATA, seq, flags)
            packet = header + payload
            self._inflight[seq] = [packet, time.monotonic(), 0]
            self._inflight_order.append(seq)
            self._raw_send(packet)
        else:
            header = struct.pack(HEADER_FMT, PKT_DATA, 0, 0)
            self._raw_send(header + payload)

    def _raw_send(self, packet: bytes):
        if self._transport and self.remote_addr:
            self._transport.sendto(packet, self.remote_addr)

    # -- receiving -----------------------------------------------------
    def _handle_packet(self, data: bytes, addr):
        self._last_recv_time = time.monotonic()
        if self.remote_addr is None:
            self.remote_addr = addr  # first contact, e.g. server side
        ptype, seq, flags = struct.unpack(HEADER_FMT, data[:HEADER_SIZE])
        body = data[HEADER_SIZE:]

        if ptype == PKT_DATA:
            if flags & FLAG_RELIABLE:
                self._send_ack(seq)
                self._deliver_in_order(seq, body)
            else:
                if self.on_message:
                    self.on_message(body)
        elif ptype == PKT_ACK:
            self._handle_ack(seq)
        elif ptype == PKT_HEARTBEAT:
            self._raw_send(struct.pack(HEADER_FMT, PKT_HEARTBEAT_ACK, seq, 0))
        elif ptype == PKT_HEARTBEAT_ACK:
            pass  # liveness already updated above

    def _send_ack(self, seq: int):
        self._raw_send(struct.pack(HEADER_FMT, PKT_ACK, seq, 0))

    def _deliver_in_order(self, seq: int, body: bytes):
        # Buffer out-of-order arrivals; flush contiguous run to the app.
        if seq < self._recv_expected:
            return  # duplicate, already delivered
        self._reorder_buf[seq] = body
        while self._recv_expected in self._reorder_buf:
            msg = self._reorder_buf.pop(self._recv_expected)
            self._recv_expected += 1
            if self.on_message:
                self.on_message(msg)

    def _handle_ack(self, seq: int):
        entry = self._inflight.pop(seq, None)
        if entry is None:
            return
        _, sent_time, tries = entry
        if tries == 0:
            self._rtt.update(time.monotonic() - sent_time)
        self._rtt.on_ack_received()
        self._record_loss(False)
        self._window_sem.release()

    # -- retransmission / loss tracking ---------------------------------
    async def _retransmit_loop(self):
        try:
            while not self._closed:
                await asyncio.sleep(0.02)
                now = time.monotonic()
                backed_off_this_round = False
                for seq in list(self._inflight.keys()):
                    packet, sent_time, tries = self._inflight[seq]
                    if now - sent_time >= self._rtt.effective_rto:
                        # "Reliable" means eventual delivery, not best-effort:
                        # a message is never silently dropped, only retried
                        # with backoff. Giving up would leave a permanent
                        # hole in the receiver's reorder buffer and stall
                        # every message after it. We warn loudly past a
                        # threshold so the app/ops layer can see a peer is
                        # badly degraded even though we keep retrying.
                        if tries == 20:
                            logger.warning(
                                "seq %d still unacked after %d tries; link "
                                "may be down, continuing to retry", seq, tries)
                        # Back off the shared RTO at most once per round
                        # (not once per packet) -- otherwise a wide window
                        # full of simultaneous timeouts makes the estimate
                        # explode to its ceiling in a single pass.
                        if not backed_off_this_round:
                            self._rtt.backoff()
                            backed_off_this_round = True
                        self._record_loss(True)
                        self._inflight[seq] = [packet, now, tries + 1]
                        self._raw_send(packet)
        except asyncio.CancelledError:
            pass

    def _record_loss(self, lost: bool):
        self._recent_losses.append(1 if lost else 0)
        if not self._recent_losses:
            return
        loss_rate = sum(self._recent_losses) / len(self._recent_losses)
        new_state = self._state
        if loss_rate > 0.4:
            new_state = LinkState.DOWN
        elif loss_rate > 0.1:
            new_state = LinkState.DEGRADED
        else:
            new_state = LinkState.HEALTHY
        if new_state != self._state:
            self._state = new_state
            logger.info("link state -> %s (loss_rate=%.2f)", new_state.value, loss_rate)
            if self.on_state_change:
                self.on_state_change(new_state)

    # -- heartbeat / liveness / reconnect --------------------------------
    async def _heartbeat_loop(self):
        try:
            while not self._closed:
                await asyncio.sleep(self.heartbeat_interval)
                if self.remote_addr:
                    self._raw_send(struct.pack(HEADER_FMT, PKT_HEARTBEAT, 0, 0))
        except asyncio.CancelledError:
            pass

    async def _liveness_loop(self):
        try:
            backoff = 0.5
            while not self._closed:
                await asyncio.sleep(0.5)
                if time.monotonic() - self._last_recv_time > self.liveness_timeout:
                    self._state = LinkState.DOWN
                    if self.on_state_change:
                        self.on_state_change(LinkState.DOWN)
                    logger.warning("link presumed down, attempting reconnect")
                    await asyncio.sleep(backoff + random.uniform(0, 0.3))
                    backoff = min(backoff * 2, 30)
                    self._resync_after_blackout()
                    if self.on_reconnect:
                        self.on_reconnect()
                    self._last_recv_time = time.monotonic()  # avoid tight loop
                else:
                    backoff = 0.5
        except asyncio.CancelledError:
            pass

    def _resync_after_blackout(self):
        # Re-send everything still in flight; a stall doesn't lose data,
        # it just delays it, since seq numbers and the reorder buffer
        # persist across the gap.
        for seq, (packet, _, tries) in list(self._inflight.items()):
            self._inflight[seq] = [packet, time.monotonic(), tries]
            self._raw_send(packet)

    @property
    def state(self) -> LinkState:
        return self._state
