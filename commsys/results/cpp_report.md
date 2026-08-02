# commsys C++ benchmark report

Generated: 2026-08-02 03:50:22 UTC

## Hardware
```
vCPUs: 1
               total        used        free      shared  buff/cache   available
Mem:           3.9Gi       356Mi       3.6Gi       4.2Mi       185Mi       3.6Gi
Swap:             0B          0B          0B
Linux vm 6.18.5 #1 SMP PREEMPT_DYNAMIC @0 x86_64 x86_64 x86_64 GNU/Linux
```

## Smoke tests
```
-- test_node_basic --
[sub] received 5 messages:
  hello-0
  hello-1
  hello-2
  hello-3
  hello-4
subscriber exit status: 0
-- test_node_udp_latest --
[udp] received 5/5
[keep_latest] sent=2829 (unpaced firehose)
[keep_latest] dispatched=770
[keep_latest] mean=0.0071ms p50=0.0066ms p99=0.0151ms max=0.0933ms
-- test_ring_stress --
[fifo ring] sent=121658 (unpaced firehose)
[fifo ring] dispatched=121658 drops=0
[fifo ring] mean=1.3582ms p50=1.2176ms p99=2.4904ms max=116.3865ms
```

## Full benchmark sweep

# commsys C++ benchmark report

Same scenario matrix as benchmark_report.py, same machine, same 2.5s steady-state duration after 0.8s discovery settle.

## 1. IMU rate sweep (single publisher -> single subscriber, 32B payload)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 500Hz shm                    |     1197 |      0 |     0.0153 MB/s |    0.0087ms |    0.0434ms |    0.8971ms |
| 1000Hz shm                   |     2300 |      0 |     0.0294 MB/s |    0.0119ms |    0.0399ms |    1.7763ms |
| 2000Hz shm                   |     4258 |      0 |     0.0545 MB/s |    0.0134ms |    0.0392ms |    2.0730ms |
| 5000Hz shm                   |     8677 |      0 |     0.1111 MB/s |    0.0141ms |    0.0341ms |    1.9431ms |
| 10000Hz shm                  |    13408 |      0 |     0.1716 MB/s |    0.0143ms |    0.0338ms |    2.0120ms |
| 500Hz udp                    |     1193 |      0 |     0.0153 MB/s |    0.0193ms |    0.0496ms |    1.6296ms |
| 1000Hz udp                   |     2286 |      0 |     0.0293 MB/s |    0.0218ms |    0.0490ms |    1.9005ms |
| 2000Hz udp                   |     4207 |      0 |     0.0538 MB/s |    0.0212ms |    0.0478ms |    0.1297ms |
| 5000Hz udp                   |     8643 |      0 |     0.1106 MB/s |    0.0215ms |    0.0437ms |    2.0087ms |
| 10000Hz udp                  |    13339 |      0 |     0.1707 MB/s |    0.0214ms |    0.0448ms |    1.7791ms |

## 2. LaserScan rate sweep (2000-point-equivalent payload, ~8KB)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 10Hz shm                     |       25 |      0 |     0.0806 MB/s |    0.0521ms |    0.0687ms |    0.0687ms |
| 20Hz shm                     |       50 |      0 |     0.1613 MB/s |    0.0435ms |    0.0769ms |    0.0769ms |
| 40Hz shm                     |      100 |      0 |     0.3226 MB/s |    0.0393ms |    0.1013ms |    0.1013ms |
| 60Hz shm                     |      149 |      0 |     0.4806 MB/s |    0.0335ms |    0.1230ms |    0.1368ms |
| 10Hz udp                     |       25 |      0 |     0.0806 MB/s |    0.0926ms |    0.1115ms |    0.1115ms |
| 20Hz udp                     |       50 |      0 |     0.1613 MB/s |    0.1199ms |    1.8007ms |    1.8007ms |
| 40Hz udp                     |      100 |      0 |     0.3226 MB/s |    0.0787ms |    0.1506ms |    0.1506ms |
| 60Hz udp                     |      149 |      0 |     0.4806 MB/s |    0.0685ms |    0.1152ms |    0.1220ms |

## 3. Unpaced firehose (worst case, no publisher pacing at all)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 64KB FIFO ring, shm          |   126328 |      0 |  4139.5159 MB/s |    1.1878ms |    2.2150ms |    9.7087ms |


## CPU core affinity comparison

Tests whether pinning the publisher and subscriber to dedicated CPU
cores (sched_setaffinity) reduces scheduling-contention tail latency,
compared to leaving scheduling up to the OS default. On a single-core
machine this is structurally a no-op (nothing to isolate from).
```
nproc=1

Only 1 CPU available -- core isolation is structurally meaningless here
(nothing to isolate the publisher and subscriber FROM; they must share
the single core regardless of any affinity setting). Running the
unpinned case only, for the record:

unpinned (only option on 1 core)         sent=  124823 dispatched=  124823 drops=     0 mean=  1.2811ms p50=  1.2470ms p99=  2.9400ms max=   8.2679ms
```
