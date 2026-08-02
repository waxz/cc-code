import asyncio
import random
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from network_resilience import ResilientChannel, _Protocol


class LossyProtocol(_Protocol):
    """Wraps datagram_received to drop packets to simulate a bad WiFi link."""
    LOSS_RATE = 0.20

    def datagram_received(self, data, addr):
        if random.random() < self.LOSS_RATE:
            return  # simulate drop
        super().datagram_received(data, addr)


async def main():
    received = []
    states = []

    def on_msg(raw):
        received.append(raw)

    def on_state(state):
        states.append(state)

    server = ResilientChannel(local_addr=("127.0.0.1", 9101), on_message=on_msg,
                               on_state_change=on_state)
    client = ResilientChannel(local_addr=("127.0.0.1", 9102),
                               remote_addr=("127.0.0.1", 9101))

    await server.start()
    await client.start()
    client.remote_addr = ("127.0.0.1", 9101)

    # monkeypatch both endpoints' underlying protocol to drop packets randomly
    loop = asyncio.get_running_loop()
    for ch in (server, client):
        old_transport = ch._transport
        old_transport._protocol.datagram_received = (
            lambda data, addr, proto=old_transport._protocol: (
                None if random.random() < 0.25 else _Protocol.datagram_received(proto, data, addr)
            )
        )

    N = 100
    for i in range(N):
        await client.send(f"msg-{i}".encode(), reliable=True)

    # give time for retransmits to land despite loss
    await asyncio.sleep(6.0)

    ok = len(received) == N and all(r == f"msg-{i}".encode() for i, r in enumerate(received))
    print(f"delivered {len(received)}/{N} messages, in-order-correct={ok}")
    print(f"link states observed: {[s.value for s in states]}")
    print(f"final client rto={client._rtt.rto:.4f}s mult={client._rtt.backoff_mult:.2f} "
          f"effective={client._rtt.effective_rto:.4f}s srtt={client._rtt.srtt}")

    await server.close()
    await client.close()


if __name__ == "__main__":
    asyncio.run(main())
