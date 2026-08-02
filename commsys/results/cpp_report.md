# commsys C++ benchmark report

Generated: 2026-08-02 04:26:46 UTC

## Hardware
```
vCPUs: 4
               total        used        free      shared  buff/cache   available
Mem:            15Gi       1.0Gi        10Gi        47Mi       4.8Gi        14Gi
Swap:          3.0Gi          0B       3.0Gi
Linux runnervmvrwv9 6.17.0-1020-azure #20~24.04.1-Ubuntu SMP Fri Jun 19 20:09:14 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
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
[keep_latest] sent=212244 (unpaced firehose)
[keep_latest] dispatched=203536
[keep_latest] mean=0.0105ms p50=0.0104ms p99=0.0129ms max=0.0472ms
-- test_ring_stress --
[fifo ring] sent=626703 (unpaced firehose)
[fifo ring] dispatched=626703 drops=0
[fifo ring] mean=0.0061ms p50=0.0049ms p99=0.0208ms max=0.8040ms
-- test_typed_api --
[sub] received 5 ImuSample messages
[sub] received 3 RawBytes blobs
typed API end-to-end test: PASS
```

## Full benchmark sweep

# commsys C++ benchmark report

Same scenario matrix as benchmark_report.py, same machine, same 2.5s steady-state duration after 0.8s discovery settle.

## 1. IMU rate sweep (single publisher -> single subscriber, 32B payload)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 500Hz shm                    |     1204 |      0 |     0.0154 MB/s |    0.0013ms |    0.0271ms |    0.0505ms |
| 1000Hz shm                   |     2359 |      0 |     0.0302 MB/s |    0.0009ms |    0.0194ms |    0.0272ms |
| 2000Hz shm                   |     4466 |      0 |     0.0572 MB/s |    0.0008ms |    0.0135ms |    0.0267ms |
| 5000Hz shm                   |     9621 |      0 |     0.1231 MB/s |    0.0007ms |    0.0097ms |    0.0265ms |
| 10000Hz shm                  |    15648 |      0 |     0.2003 MB/s |    0.0006ms |    0.0083ms |    0.0279ms |
| 500Hz udp                    |     1206 |      0 |     0.0154 MB/s |    0.0128ms |    0.0237ms |    0.0664ms |
| 1000Hz udp                   |     2358 |      0 |     0.0302 MB/s |    0.0071ms |    0.0125ms |    0.0619ms |
| 2000Hz udp                   |     4463 |      0 |     0.0571 MB/s |    0.0067ms |    0.0137ms |    0.0600ms |
| 5000Hz udp                   |     9646 |      0 |     0.1235 MB/s |    0.0059ms |    0.0097ms |    0.0604ms |
| 10000Hz udp                  |    15624 |      0 |     0.2000 MB/s |    0.0063ms |    0.0113ms |    0.0584ms |

## 2. LaserScan rate sweep (2000-point-equivalent payload, ~8KB)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 10Hz shm                     |       25 |      0 |     0.0806 MB/s |    0.0352ms |    0.0829ms |    0.0829ms |
| 20Hz shm                     |       50 |      0 |     0.1613 MB/s |    0.0277ms |    0.0549ms |    0.0549ms |
| 40Hz shm                     |      100 |      0 |     0.3226 MB/s |    0.0214ms |    0.0547ms |    0.0547ms |
| 60Hz shm                     |      150 |      0 |     0.4838 MB/s |    0.0195ms |    0.0442ms |    0.0548ms |
| 10Hz udp                     |       25 |      0 |     0.0806 MB/s |    0.0776ms |    0.1164ms |    0.1164ms |
| 20Hz udp                     |       50 |      0 |     0.1613 MB/s |    0.0650ms |    0.1115ms |    0.1115ms |
| 40Hz udp                     |      100 |      0 |     0.3226 MB/s |    0.0528ms |    0.1064ms |    0.1064ms |
| 60Hz udp                     |      150 |      0 |     0.4838 MB/s |    0.0490ms |    0.1038ms |    0.1167ms |

## 3. Unpaced firehose (worst case, no publisher pacing at all)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 64KB FIFO ring, shm          |   489337 |      0 | 16034.5948 MB/s |    0.0067ms |    0.0219ms |    0.7406ms |


## CPU core affinity comparison

Tests whether pinning the publisher and subscriber to dedicated CPU
cores (sched_setaffinity) reduces scheduling-contention tail latency,
compared to leaving scheduling up to the OS default. On a single-core
machine this is structurally a no-op (nothing to isolate from).
```
nproc=4

=== Unpinned (OS default scheduling) ===
unpinned                                 sent=  542435 dispatched=  542435 drops=     0 mean=  0.0070ms p50=  0.0054ms p99=  0.0223ms max=   1.0756ms
unpinned                                 sent=  624588 dispatched=  624588 drops=     0 mean=  0.0065ms p50=  0.0049ms p99=  0.0219ms max=   1.0818ms
unpinned                                 sent=  412812 dispatched=  412812 drops=     0 mean=  0.0073ms p50=  0.0066ms p99=  0.0220ms max=   0.7409ms

=== Pinned: publisher->CPU0, subscriber->CPU1 ===
pinned                                   sent=  394541 dispatched=  394541 drops=     0 mean=  0.0096ms p50=  0.0072ms p99=  0.0384ms max=   1.0436ms
pinned                                   sent=  357922 dispatched=  357922 drops=     0 mean=  0.0094ms p50=  0.0074ms p99=  0.0385ms max=   1.0569ms
pinned                                   sent=  370040 dispatched=  370040 drops=     0 mean=  0.0093ms p50=  0.0073ms p99=  0.0384ms max=   1.0442ms
```
