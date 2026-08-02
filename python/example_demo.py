"""
example_demo.py
----------------
Minimal end-to-end demonstration of UnifiedTransport:

  - "worker"  is on the same host  -> shared-memory ring buffer
  - "gateway" is on a remote host  -> resilient UDP channel

Run this file directly. It starts a small in-process "remote" peer on
a different UDP port to stand in for a real remote host, and a local
worker process using shared memory, then sends a few messages over
each path.
"""

import asyncio
import multiprocessing as mp
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from transport import UnifiedTransport
from network_resilience import ResilientChannel


def local_worker(rx_name, tx_name):
    """Runs in a separate OS process; reads work items, writes results,
    entirely through shared memory -- no network stack involved."""
    from shared_memory_ipc import SPSCRingBuffer
    from serialization import Serializer
    FLAG_SERIALIZED = 0  # must match transport.py's FLAG_SERIALIZED
    ser = Serializer()
    rx = SPSCRingBuffer(rx_name, create=False)
    tx = SPSCRingBuffer(tx_name, create=False)
    while True:
        raw = rx.read(timeout=10.0)
        if raw is None:
            break
        job = ser.loads(raw[1:])  # raw[0] is UnifiedTransport's format flag
        result = {"job_id": job["job_id"], "result": job["n"] ** 2}
        tx.write(bytes([FLAG_SERIALIZED]) + ser.dumps(result))
    rx.close()
    tx.close()


async def remote_peer_stub(port_recv, port_send_to):
    """Stands in for a peer on another machine, echoing what it gets."""
    from serialization import Serializer
    ser = Serializer()
    ch = ResilientChannel(local_addr=("127.0.0.1", port_recv))

    def on_msg(raw):
        msg = ser.loads(raw)
        ack = ser.dumps({"type": "ack", "of": msg})
        asyncio.create_task(ch.send(ack))

    ch.on_message = on_msg
    await ch.start()
    return ch


async def main():
    received = []

    def on_message(peer_id, message):
        received.append((peer_id, message))
        print(f"[app] from {peer_id}: {message}")

    transport = UnifiedTransport(on_message=on_message)

    # -- local peer: shared memory -----------------------------------
    # Rings must exist (create=True happens inside connect_local) before
    # the worker process tries to open them with create=False.
    transport.connect_local("worker", ring_name_tx="worker_rx", ring_name_rx="worker_tx")
    p = mp.Process(target=local_worker, args=("worker_rx", "worker_tx"))
    p.start()

    for i in range(3):
        await transport.send("worker", {"job_id": i, "n": i + 2})

    # -- remote peer: resilient network channel ------------------------
    remote = await remote_peer_stub(port_recv=9201, port_send_to=9200)
    await transport.connect_remote("gateway", local_addr=("127.0.0.1", 9200),
                                    remote_addr=("127.0.0.1", 9201))
    await transport.send("gateway", {"type": "ping", "seq": 1})

    await asyncio.sleep(1.0)
    print(f"total messages received by app: {len(received)}")

    await transport.close()
    await remote.close()
    p.join(timeout=2)
    if p.is_alive():
        p.terminate()


if __name__ == "__main__":
    asyncio.run(main())
