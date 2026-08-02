import multiprocessing as mp
import time
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shared_memory_ipc import SPSCRingBuffer


def producer(name):
    ring = SPSCRingBuffer(name, capacity=1 << 16, create=False)
    for i in range(2000):
        ring.write(f"msg-{i}".encode())
    ring.mark_closed()
    ring.close()


def main():
    ring = SPSCRingBuffer("test_ring", capacity=1 << 16, create=True)
    p = mp.Process(target=producer, args=("test_ring",))
    p.start()

    received = 0
    t0 = time.monotonic()
    while True:
        msg = ring.read(timeout=3.0)
        if msg is None:
            break
        assert msg == f"msg-{received}".encode(), (msg, received)
        received += 1
    dt = time.monotonic() - t0
    p.join()
    ring.close()
    ring.unlink()
    print(f"OK: received {received} messages in {dt:.4f}s "
          f"({received/dt:.0f} msg/s)")


if __name__ == "__main__":
    main()
