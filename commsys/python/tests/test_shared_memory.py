"""
tests/test_shared_memory.py
----------------------------
Unit tests for shared_memory_ipc.py: basic roundtrip, ring wraparound,
boundary/edge cases, close/unlink lifecycle, and MPMC correctness with
concurrent producers and consumers.
"""

import multiprocessing as mp
import sys
import os
import time
import threading
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared_memory_ipc import SPSCRingBuffer, MPMCQueue


def unique_name(prefix="ring"):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@pytest.fixture
def ring():
    name = unique_name()
    r = SPSCRingBuffer(name, capacity=4096, create=True)
    yield r
    r.mark_closed()
    r.close()
    r.unlink()


class TestBasicRoundtrip:
    def test_single_message(self, ring):
        ring.write(b"hello")
        assert ring.read(timeout=1.0) == b"hello"

    def test_empty_message(self, ring):
        ring.write(b"")
        assert ring.read(timeout=1.0) == b""

    def test_fifo_order_preserved(self, ring):
        msgs = [f"msg-{i}".encode() for i in range(50)]
        for m in msgs:
            ring.write(m)
        for m in msgs:
            assert ring.read(timeout=1.0) == m

    def test_read_on_empty_times_out(self, ring):
        with pytest.raises(TimeoutError):
            ring.read(timeout=0.2)

    def test_read_returns_none_after_close_when_empty(self, ring):
        ring.mark_closed()
        assert ring.read(timeout=1.0) is None


class TestWraparoundAndCapacity:
    def test_many_small_messages_wrap_the_buffer(self, ring):
        # capacity=4096; each message here costs 4(len)+7(payload)=11
        # bytes. Writing 1000 of them (11,000 bytes total) through a
        # 4096-byte ring forces many wraps -- but only works if reads
        # keep pace with writes, so producer and consumer run
        # concurrently (as they would across real processes) rather
        # than writing everything up front.
        n = 1000
        received = []

        def produce():
            for i in range(n):
                ring.write(str(i % 100).zfill(7).encode())

        def consume():
            for _ in range(n):
                received.append(ring.read(timeout=2.0))

        t_prod = threading.Thread(target=produce)
        t_cons = threading.Thread(target=consume)
        t_cons.start()
        t_prod.start()
        t_prod.join(timeout=5)
        t_cons.join(timeout=5)

        assert len(received) == n
        for i in range(n):
            assert received[i] == str(i % 100).zfill(7).encode()

    def test_message_that_itself_wraps_the_data_region(self):
        # Force a write whose payload straddles the end of the ring's
        # data region (exercises the two-piece copy in _write_bytes /
        # _read_bytes), by first burning off some offset with small
        # writes/reads, then writing something large.
        name = unique_name()
        r = SPSCRingBuffer(name, capacity=64, create=True)
        try:
            r.write(b"0123456789")   # 4+10=14 bytes, advances write_idx
            assert r.read(timeout=1.0) == b"0123456789"  # advances read_idx too
            big = bytes(range(50))   # 4+50=54 bytes; with 14 bytes of
                                      # headroom already consumed, this
                                      # write's payload wraps past the
                                      # physical end of the 64-byte region
            r.write(big)
            assert r.read(timeout=1.0) == big
        finally:
            r.mark_closed()
            r.close()
            r.unlink()

    def test_payload_larger_than_capacity_rejected(self, ring):
        with pytest.raises(ValueError):
            ring.try_write(b"x" * 100_000)

    def test_full_ring_blocks_then_times_out(self):
        name = unique_name()
        r = SPSCRingBuffer(name, capacity=64, create=True)
        try:
            # fill until try_write reports full
            count = 0
            while r.try_write(b"x" * 10):
                count += 1
                if count > 100:
                    pytest.fail("ring never reported full")
            with pytest.raises(TimeoutError):
                r.write(b"one more", timeout=0.2)
        finally:
            r.mark_closed()
            r.close()
            r.unlink()


class TestCrossProcess:
    def test_producer_process_consumer_in_test(self):
        name = unique_name()
        parent_ring = SPSCRingBuffer(name, capacity=1 << 16, create=True)

        def producer(ring_name):
            r = SPSCRingBuffer(ring_name, create=False)
            for i in range(500):
                r.write(f"m{i}".encode())
            r.mark_closed()
            r.close()

        p = mp.Process(target=producer, args=(name,))
        p.start()
        received = 0
        while True:
            msg = parent_ring.read(timeout=3.0)
            if msg is None:
                break
            assert msg == f"m{received}".encode()
            received += 1
        p.join(timeout=5)
        assert received == 500
        parent_ring.mark_closed()
        parent_ring.close()
        parent_ring.unlink()


class TestMPMC:
    def test_multiple_producers_multiple_consumers_no_loss_no_dup(self):
        name = unique_name()
        base_ring = SPSCRingBuffer(name, capacity=1 << 18, create=True)
        lock = mp.Lock()
        n_producers = 4
        n_consumers = 3
        msgs_per_producer = 200
        total = n_producers * msgs_per_producer

        results = mp.Manager().list()
        stop_flag = mp.Manager().Event()

        def produce(idx):
            ring = SPSCRingBuffer(name, create=False)
            q = MPMCQueue(ring, lock)
            for i in range(msgs_per_producer):
                q.write(f"p{idx}-{i}".encode())

        def consume():
            ring = SPSCRingBuffer(name, create=False)
            q = MPMCQueue(ring, lock)
            local = []
            while not stop_flag.is_set():
                try:
                    msg = q.read(timeout=0.3)
                except TimeoutError:
                    continue
                if msg is None:
                    break
                local.append(msg.decode())
            results.extend(local)

        consumers = [mp.Process(target=consume) for _ in range(n_consumers)]
        for c in consumers:
            c.start()

        producers = [mp.Process(target=produce, args=(i,)) for i in range(n_producers)]
        for p in producers:
            p.start()
        for p in producers:
            p.join(timeout=10)

        # give consumers time to drain, then signal stop
        deadline = time.monotonic() + 5.0
        while len(results) < total and time.monotonic() < deadline:
            time.sleep(0.05)
        stop_flag.set()
        for c in consumers:
            c.join(timeout=3)
            if c.is_alive():
                c.terminate()

        base_ring.mark_closed()
        base_ring.close()
        base_ring.unlink()

        assert len(results) == total, f"expected {total}, got {len(results)}"
        assert len(set(results)) == total, "duplicate or corrupted messages detected"
        expected = {f"p{i}-{j}" for i in range(n_producers) for j in range(msgs_per_producer)}
        assert set(results) == expected


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
