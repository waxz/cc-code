# commsys C++ benchmark report

Generated: 2026-08-02 03:55:24 UTC

## Hardware
```
vCPUs: 4
               total        used        free      shared  buff/cache   available
Mem:            15Gi       997Mi        11Gi        45Mi       3.2Gi        14Gi
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
[keep_latest] sent=351338 (unpaced firehose)
[keep_latest] dispatched=347010
[keep_latest] mean=0.0067ms p50=0.0066ms p99=0.0088ms max=0.0687ms
-- test_ring_stress --
[fifo ring] sent=449542 (unpaced firehose)
[fifo ring] dispatched=449542 drops=0
[fifo ring] mean=0.0080ms p50=0.0061ms p99=0.0269ms max=0.9107ms
```

## Full benchmark sweep

# commsys C++ benchmark report

Same scenario matrix as benchmark_report.py, same machine, same 2.5s steady-state duration after 0.8s discovery settle.

## 1. IMU rate sweep (single publisher -> single subscriber, 32B payload)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 500Hz shm                    |     1210 |      0 |     0.0155 MB/s |    0.0010ms |    0.0242ms |    0.0283ms |
| 1000Hz shm                   |     2343 |      0 |     0.0300 MB/s |    0.0010ms |    0.0229ms |    0.0309ms |
| 2000Hz shm                   |     4424 |      0 |     0.0566 MB/s |    0.0008ms |    0.0166ms |    0.0449ms |
| 5000Hz shm                   |     9355 |      0 |     0.1197 MB/s |    0.0008ms |    0.0155ms |    0.0705ms |
| 10000Hz shm                  |    15015 |      0 |     0.1922 MB/s |    0.0008ms |    0.0131ms |    0.0599ms |
| 500Hz udp                    |     1208 |      0 |     0.0155 MB/s |    0.0112ms |    0.0172ms |    0.0798ms |
| 1000Hz udp                   |     2342 |      0 |     0.0300 MB/s |    0.0092ms |    0.0155ms |    0.0563ms |
| 2000Hz udp                   |     4406 |      0 |     0.0564 MB/s |    0.0089ms |    0.0160ms |    0.0643ms |
| 5000Hz udp                   |     9404 |      0 |     0.1204 MB/s |    0.0079ms |    0.0148ms |    0.0655ms |
| 10000Hz udp                  |    15021 |      0 |     0.1923 MB/s |    0.0082ms |    0.0145ms |    0.0679ms |

## 2. LaserScan rate sweep (2000-point-equivalent payload, ~8KB)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 10Hz shm                     |       25 |      0 |     0.0806 MB/s |    0.0346ms |    0.0493ms |    0.0493ms |
| 20Hz shm                     |       50 |      0 |     0.1613 MB/s |    0.0337ms |    0.0518ms |    0.0518ms |
| 40Hz shm                     |      100 |      0 |     0.3226 MB/s |    0.0311ms |    0.0517ms |    0.0517ms |
| 60Hz shm                     |      150 |      0 |     0.4838 MB/s |    0.0246ms |    0.0409ms |    0.0581ms |
| 10Hz udp                     |       25 |      0 |     0.0806 MB/s |    0.0878ms |    0.1188ms |    0.1188ms |
| 20Hz udp                     |       50 |      0 |     0.1613 MB/s |    0.0837ms |    0.1173ms |    0.1173ms |
| 40Hz udp                     |      100 |      0 |     0.3226 MB/s |    0.0834ms |    0.1221ms |    0.1221ms |
| 60Hz udp                     |      149 |      0 |     0.4806 MB/s |    0.0803ms |    0.0959ms |    0.1096ms |

## 3. Unpaced firehose (worst case, no publisher pacing at all)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 64KB FIFO ring, shm          |   409466 |      0 | 13417.3819 MB/s |    0.0080ms |    0.0271ms |    0.6617ms |


## CPU core affinity comparison

Tests whether pinning the publisher and subscriber to dedicated CPU
cores (sched_setaffinity) reduces scheduling-contention tail latency,
compared to leaving scheduling up to the OS default. On a single-core
machine this is structurally a no-op (nothing to isolate from).
```
nproc=4

=== Unpinned (OS default scheduling) ===
unpinned                                 sent=  489487 dispatched=  489487 drops=     0 mean=  0.0079ms p50=  0.0057ms p99=  0.0267ms max=   0.9504ms
unpinned                                 sent=  497631 dispatched=  497631 drops=     0 mean=  0.0072ms p50=  0.0057ms p99=  0.0262ms max=   0.9048ms
unpinned                                 sent=  497741 dispatched=  497741 drops=     0 mean=  0.0078ms p50=  0.0057ms p99=  0.0264ms max=   0.9234ms

=== Pinned: publisher->CPU0, subscriber->CPU1 ===
pinned                                   sent=  337001 dispatched=  337001 drops=     0 mean=  0.0143ms p50=  0.0085ms p99=  0.0513ms max=   1.2206ms
pinned                                   sent=  324914 dispatched=  324914 drops=     0 mean=  0.0142ms p50=  0.0086ms p99=  0.0502ms max=   1.3018ms
pinned                                   sent=  323996 dispatched=  323996 drops=     0 mean=  0.0137ms p50=  0.0086ms p99=  0.0489ms max=   1.2537ms
```
