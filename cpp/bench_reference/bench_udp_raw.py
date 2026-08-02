"""bench_udp_raw.py -- Python equivalent of bench_udp_raw.cpp: raw
UDP sendto() throughput, no asyncio, no reliability layer, to isolate
the syscall floor from Python interpreter overhead specifically."""
import socket
import time

N = 200_000
payload = b"x" * 64
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
addr = ("127.0.0.1", 23456)

t0 = time.perf_counter()
for _ in range(N):
    sock.sendto(payload, addr)
t1 = time.perf_counter()
secs = t1 - t0
print(f"=== Python raw UDP sendto(), no receiver, N={N} ===")
print(f"  {secs:.4f}s total, {N/secs:.0f} sendto/s, {secs*1e9/N:.0f}ns/call")
