"""
shared_memory_ipc.py
---------------------
High-efficiency local transport for processes on the SAME host.

Two primitives:

1. SPSCRingBuffer  - single-producer/single-consumer, lock-free.
   The classic zero-syscall-on-hot-path ring buffer: producer only
   ever writes `write_idx`, consumer only ever writes `read_idx`, so
   there's no data race on the control fields as long as each 64-bit
   index write/read is naturally aligned (guaranteed by ctypes here).
   This is the fastest path — use it for a fixed pipeline stage
   (e.g. capture -> processing).

2. MPMCQueue - multi-producer/multi-consumer, built on top of the
   same shared ring buffer but guarded by a multiprocessing.Lock.
   Use this when more than one writer or reader touches the same
   channel. Requires the Lock to be created by a common parent and
   passed to children (standard multiprocessing.Process usage) since
   Python has no portable named cross-process mutex without a third
   -party dependency (posix_ipc). See NOTES.md in README for the
   production alternative (posix_ipc named semaphore / eventfd).

Both use a doubled-modulus index scheme (mod 2*capacity) to
distinguish "full" from "empty" without wasting a slot or needing an
extra counter.
"""

import ctypes
import time
from multiprocessing import shared_memory


def _unregister_from_resource_tracker(shm: shared_memory.SharedMemory):
    """Python's resource_tracker (pre-3.13, which has no `track=`
    kwarg yet) registers every SharedMemory handle for cleanup on
    creation *and* on attach, even though only the creator should ever
    unlink it. Left alone, every attaching process independently
    thinks it owns cleanup, which produces harmless but noisy
    "leaked shared_memory objects" warnings when a process forked from
    the creator (or a separate attach-only consumer) exits. This
    leaves the segment itself and its data untouched -- it only opts
    this process's resource_tracker out of also trying to remove it."""
    try:
        from multiprocessing import resource_tracker
        resource_tracker.unregister(shm._name, "shared_memory")
    except Exception:
        pass  # best-effort cleanliness, never worth failing over


class RingHeader(ctypes.Structure):
    _fields_ = [
        ("write_idx", ctypes.c_uint64),
        ("read_idx", ctypes.c_uint64),
        ("capacity", ctypes.c_uint64),
        ("closed", ctypes.c_uint8),
    ]


HEADER_SIZE = ctypes.sizeof(RingHeader)


class RingFull(Exception):
    pass


class SPSCRingBuffer:
    def __init__(self, name: str, capacity: int = 1 << 20, create: bool = False):
        total_size = HEADER_SIZE + capacity
        if create:
            try:
                shared_memory.SharedMemory(name=name).unlink()
            except FileNotFoundError:
                pass
            self._shm = shared_memory.SharedMemory(name=name, create=True, size=total_size)
            self._header = RingHeader.from_buffer(self._shm.buf)
            self._header.write_idx = 0
            self._header.read_idx = 0
            self._header.capacity = capacity
            self._header.closed = 0
        else:
            deadline = time.monotonic() + 2.0
            while True:
                try:
                    self._shm = shared_memory.SharedMemory(name=name, create=False)
                    break
                except ValueError as e:
                    # Same transient race as discovery.py: the creator's
                    # shm_open() and ftruncate() aren't atomic, so an
                    # attacher can briefly see a zero-sized segment.
                    if "empty file" not in str(e) or time.monotonic() > deadline:
                        raise
                    time.sleep(0.002)
            # Only the creating process should be responsible for the
            # final unlink(); Python's resource_tracker otherwise
            # registers cleanup duty in *every* process that so much as
            # attaches, which produces spurious "leaked shared_memory
            # objects" warnings when several attach-only processes (or
            # the create=True process, forked into children) exit.
            _unregister_from_resource_tracker(self._shm)
            self._header = RingHeader.from_buffer(self._shm.buf)
            # Race: shm_open()+ftruncate() makes a freshly created
            # segment attachable to other processes via its name before
            # the creator has actually written its header fields (the
            # OS zero-fills new segments, and zero is not a valid
            # header -- capacity=0 would divide-by-zero on first use).
            # Wait briefly for the creator to finish initializing.
            deadline = time.monotonic() + 2.0
            while self._header.capacity == 0:
                if time.monotonic() > deadline:
                    raise TimeoutError(
                        f"shared memory segment {name!r} exists but was never "
                        f"initialized (creator crashed before writing its header?)")
                time.sleep(0.001)
            capacity = self._header.capacity

        self.capacity = capacity
        self._data = (ctypes.c_ubyte * self.capacity).from_buffer(self._shm.buf, HEADER_SIZE)
        self._data_addr = ctypes.addressof(self._data)

    # -- lifecycle -----------------------------------------------------
    def close(self):
        # ctypes structures/arrays built with from_buffer() hold a live
        # reference (an "exported pointer") into the shm's mmap buffer.
        # Drop them first or SharedMemory.close() raises BufferError.
        self._header = None
        self._data = None
        self._shm.close()

    def unlink(self):
        try:
            self._shm.unlink()
        except FileNotFoundError:
            pass

    def mark_closed(self):
        self._header.closed = 1

    @property
    def is_closed(self) -> bool:
        return self._header.closed == 1

    # -- core ops --------------------------------------------------------
    def _free_space(self, w, r):
        used = (w - r) % (2 * self.capacity)
        return self.capacity - used

    def try_write(self, payload: bytes) -> bool:
        need = 4 + len(payload)
        if need - 4 > self.capacity:
            raise ValueError("payload larger than ring capacity")
        w = self._header.write_idx
        r = self._header.read_idx
        if self._free_space(w, r) < need:
            return False
        self._write_bytes(w, len(payload).to_bytes(4, "little"))
        self._write_bytes(w + 4, payload)
        self._header.write_idx = (w + need) % (2 * self.capacity)
        return True

    def write(self, payload: bytes, timeout: float = 5.0):
        deadline = time.monotonic() + timeout
        spins = 0
        while not self.try_write(payload):
            if time.monotonic() > deadline:
                raise TimeoutError("ring buffer full: consumer too slow")
            spins += 1
            self._backoff(spins)

    def try_read(self):
        w = self._header.write_idx
        r = self._header.read_idx
        if w == r:
            return None
        length = int.from_bytes(self._read_bytes(r, 4), "little")
        payload = self._read_bytes(r + 4, length)
        self._header.read_idx = (r + 4 + length) % (2 * self.capacity)
        return payload

    def read(self, timeout: float = 5.0):
        deadline = time.monotonic() + timeout
        spins = 0
        while True:
            msg = self.try_read()
            if msg is not None:
                return msg
            if self.is_closed:
                return None
            if time.monotonic() > deadline:
                raise TimeoutError("no data: producer stalled")
            spins += 1
            self._backoff(spins)

    @staticmethod
    def _backoff(spins: int):
        # tight spin (lowest latency) -> yield timeslice -> short sleep
        if spins < 1000:
            return
        elif spins < 5000:
            time.sleep(0)
        else:
            time.sleep(0.0005)

    def _write_bytes(self, pos: int, data: bytes):
        # ctypes array slice assignment (self._data[a:b] = data) looks
        # like it should be a bulk memcpy but isn't -- CPython's ctypes
        # falls back to an element-by-element path for this case, which
        # measured ~215x slower than a real memcpy (0.036 GB/s vs 7.7
        # GB/s on this machine). ctypes.memmove goes straight to the C
        # memmove() the way this is supposed to work.
        n = len(data)
        pos = pos % self.capacity
        end = pos + n
        if end <= self.capacity:
            ctypes.memmove(self._data_addr + pos, data, n)
        else:
            first = self.capacity - pos
            ctypes.memmove(self._data_addr + pos, data, first)
            ctypes.memmove(self._data_addr, data[first:], n - first)

    def _read_bytes(self, pos: int, n: int) -> bytes:
        # Same story as _write_bytes: ctypes.string_at() is a real bulk
        # copy (measured ~25 GB/s here) versus slicing self._data and
        # wrapping the result in bytes(), which pays the same
        # element-wise tax on the way out.
        pos = pos % self.capacity
        end = pos + n
        if end <= self.capacity:
            return ctypes.string_at(self._data_addr + pos, n)
        first = self.capacity - pos
        return (ctypes.string_at(self._data_addr + pos, first)
                + ctypes.string_at(self._data_addr, n - first))


class LatestValueSlot:
    """Lock-free single-slot 'latest value wins' shared memory
    primitive, for topics where a subscriber wants the most recent
    sample and does NOT want to wait through a backlog to get it --
    the standard real-time answer to bufferbloat: bound staleness
    instead of trying to bound every message's individual latency.

    Uses the classic seqlock pattern: the writer increments a
    sequence counter (odd = write in progress), writes the payload,
    then increments again (even = stable). The reader reads the
    sequence before and after copying the payload; if either read
    caught an odd value, or the value changed mid-copy, it retries.
    This makes writes wait-free (a writer never blocks on a slow or
    even completely stalled reader -- it just overwrites) and makes
    reads very likely to succeed on the first attempt, with a bounded
    number of retries in the rare case of a genuine race, rather than
    the unbounded queueing delay a FIFO ring can accumulate under a
    publisher that outpaces its consumer.

    Tradeoff, stated plainly: a slow reader can miss intermediate
    values entirely (it only ever sees "the latest one", never a
    backlog) -- appropriate for a live sensor feed where the freshest
    reading matters more than not missing any single one, and wrong
    for anything that needs every message (event logs, financial
    transactions, etc.), which is exactly what SPSCRingBuffer is for.
    """

    def __init__(self, name: str, capacity: int = 1 << 16, create: bool = False):
        total_size = HEADER_SIZE + capacity
        if create:
            try:
                shared_memory.SharedMemory(name=name).unlink()
            except FileNotFoundError:
                pass
            self._shm = shared_memory.SharedMemory(name=name, create=True, size=total_size)
            self._header = RingHeader.from_buffer(self._shm.buf)
            self._header.write_idx = 0  # doubles as the seqlock counter here
            self._header.read_idx = 0   # unused for this primitive
            self._header.capacity = capacity
            self._header.closed = 0
        else:
            self._shm = shared_memory.SharedMemory(name=name, create=False)
            _unregister_from_resource_tracker(self._shm)
            self._header = RingHeader.from_buffer(self._shm.buf)
            deadline = time.monotonic() + 2.0
            while self._header.capacity == 0:
                if time.monotonic() > deadline:
                    raise TimeoutError(f"shared memory segment {name!r} exists but was never initialized")
                time.sleep(0.001)
            capacity = self._header.capacity

        self.capacity = capacity
        self._data = (ctypes.c_ubyte * self.capacity).from_buffer(self._shm.buf, HEADER_SIZE)
        self._data_addr = ctypes.addressof(self._data)
        self._len_addr = self._data_addr  # first 4 bytes of the data region: payload length

    def close(self):
        self._header = None
        self._data = None
        self._shm.close()

    def unlink(self):
        try:
            self._shm.unlink()
        except FileNotFoundError:
            pass

    def mark_closed(self):
        self._header.closed = 1

    @property
    def is_closed(self) -> bool:
        return self._header.closed == 1

    def write(self, payload: bytes):
        n = len(payload)
        if n + 4 > self.capacity:
            raise ValueError("payload larger than slot capacity")
        seq = self._header.write_idx
        self._header.write_idx = seq + 1  # now odd: write in progress
        ctypes.memmove(self._data_addr, len(payload).to_bytes(4, "little"), 4)
        ctypes.memmove(self._data_addr + 4, payload, n)
        self._header.write_idx = seq + 2  # now even again: stable

    def try_read(self):
        """Returns the latest payload, or None if nothing has been
        written yet or a persistent writer race prevented a clean
        read within a bounded number of retries (extremely rare --
        this is not a "slow consumer" signal, just a torn-read guard)."""
        for _ in range(50):
            s1 = self._header.write_idx
            if s1 & 1:
                continue  # writer mid-update; retry immediately
            n = int.from_bytes(ctypes.string_at(self._data_addr, 4), "little")
            if n == 0:
                return None
            payload = ctypes.string_at(self._data_addr + 4, n)
            s2 = self._header.write_idx
            if s1 == s2:
                return payload
            # a write happened during our read; the payload we just
            # copied may be torn, retry
        return None


class MPMCQueue:
    """Multiple producers / multiple consumers sharing one ring buffer.
    Correctness requires `lock` to be a multiprocessing.Lock created by
    a common ancestor process (fork/spawn) and passed to each worker.
    """

    def __init__(self, ring: SPSCRingBuffer, lock):
        self.ring = ring
        self.lock = lock

    def write(self, payload: bytes, timeout: float = 5.0):
        deadline = time.monotonic() + timeout
        while True:
            with self.lock:
                if self.ring.try_write(payload):
                    return
            if time.monotonic() > deadline:
                raise TimeoutError("MPMC ring full")
            time.sleep(0.0005)

    def read(self, timeout: float = 5.0):
        deadline = time.monotonic() + timeout
        while True:
            with self.lock:
                msg = self.ring.try_read()
            if msg is not None:
                return msg
            if self.ring.is_closed:
                return None
            if time.monotonic() > deadline:
                raise TimeoutError("MPMC ring empty")
            time.sleep(0.0005)
