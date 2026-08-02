"""tests/test_latest_value_slot.py"""
import multiprocessing as mp
import sys
import os
import time
import uuid

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from shared_memory_ipc import LatestValueSlot


def uniq():
    return f"lvs_{uuid.uuid4().hex[:10]}"


class TestLatestValueSlot:
    def test_read_before_any_write_returns_none(self):
        name = uniq()
        slot = LatestValueSlot(name, capacity=4096, create=True)
        try:
            assert slot.try_read() is None
        finally:
            slot.close(); slot.unlink()

    def test_single_write_then_read(self):
        name = uniq()
        slot = LatestValueSlot(name, capacity=4096, create=True)
        try:
            slot.write(b"hello")
            assert slot.try_read() == b"hello"
        finally:
            slot.close(); slot.unlink()

    def test_repeated_reads_return_same_value_until_overwritten(self):
        name = uniq()
        slot = LatestValueSlot(name, capacity=4096, create=True)
        try:
            slot.write(b"first")
            assert slot.try_read() == b"first"
            assert slot.try_read() == b"first"  # no new write; same value
            slot.write(b"second")
            assert slot.try_read() == b"second"
        finally:
            slot.close(); slot.unlink()

    def test_writer_never_blocks_regardless_of_reader(self):
        """The whole point: a writer racing ahead of a reader that
        never even looks must never block or raise."""
        name = uniq()
        slot = LatestValueSlot(name, capacity=1024, create=True)
        try:
            t0 = time.monotonic()
            for i in range(10000):
                slot.write(f"m{i}".encode())
            dt = time.monotonic() - t0
            assert dt < 2.0  # no reader ever touched this; must not stall
            assert slot.try_read() == b"m9999"
        finally:
            slot.close(); slot.unlink()

    def test_payload_larger_than_capacity_rejected(self):
        name = uniq()
        slot = LatestValueSlot(name, capacity=64, create=True)
        try:
            with pytest.raises(ValueError):
                slot.write(b"x" * 1000)
        finally:
            slot.close(); slot.unlink()

    def test_cross_process_reader_always_gets_a_recent_value(self):
        """A slow/late reader should see *some* valid, non-torn value
        from near the end of a fast writer's run -- never garbage,
        and never forced to wait through a backlog to get there."""
        name = uniq()

        def writer(nm):
            s = LatestValueSlot(nm, create=False)
            for i in range(5000):
                s.write(f"msg-{i}".encode())
            s.mark_closed()
            s.close()

        slot = LatestValueSlot(name, capacity=4096, create=True)
        try:
            p = mp.Process(target=writer, args=(name,))
            p.start()
            time.sleep(0.3)  # let the writer race far ahead
            latest = slot.try_read()
            p.join(timeout=5)
            assert latest is not None
            assert latest.startswith(b"msg-")
            seen_idx = int(latest.split(b"-")[1])
            # Should be recent, not stuck near the start -- proves the
            # reader isn't dragging through a backlog.
            assert seen_idx > 2000
        finally:
            slot.close(); slot.unlink()

    def test_never_torn_under_concurrent_write_read(self):
        """Stress the seqlock: a background writer hammering the slot
        while the foreground repeatedly reads must never observe a
        value that isn't exactly one of the ones actually written."""
        name = uniq()
        valid = {f"payload-{i:06d}".encode() for i in range(2000)}

        def writer(nm):
            s = LatestValueSlot(nm, create=False)
            for i in range(2000):
                s.write(f"payload-{i:06d}".encode())
            s.mark_closed()
            s.close()

        slot = LatestValueSlot(name, capacity=4096, create=True)
        try:
            p = mp.Process(target=writer, args=(name,))
            p.start()
            for _ in range(3000):
                v = slot.try_read()
                if v is not None:
                    assert v in valid, f"torn/corrupt read: {v!r}"
            p.join(timeout=5)
        finally:
            slot.close(); slot.unlink()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
