# commsys C++ benchmark report

Generated: 2026-08-08 04:00:24 UTC

## Hardware
```
vCPUs: 4
               total        used        free      shared  buff/cache   available
Mem:            15Gi       979Mi        11Gi        46Mi       3.2Gi        14Gi
Swap:          3.0Gi          0B       3.0Gi
Linux runnervmvrwv9 6.17.0-1020-azure #20~24.04.1-Ubuntu SMP Fri Jun 19 20:09:14 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
```

## Unit tests (ctest / Catch2)
```
Test project /home/runner/work/cc-code/cc-code/commsys/cpp/build
    Start 1: commsys_tests
1/1 Test #1: commsys_tests ....................   Passed   27.38 sec

100% tests passed, 0 tests failed out of 1

Total Test time (real) =  27.49 sec
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
[keep_latest] sent=361179 (unpaced firehose)
[keep_latest] dispatched=359143
[keep_latest] mean=0.0067ms p50=0.0065ms p99=0.0097ms max=0.2062ms
-- test_ring_stress --
[fifo ring] sent=289105 (unpaced firehose)
[fifo ring] dispatched=289105 drops=0
[fifo ring] mean=0.0101ms p50=0.0085ms p99=0.0292ms max=0.9405ms
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
| 500Hz shm                    |     1209 |      0 |     0.0155 MB/s |    0.0010ms |    0.0247ms |    0.0731ms |
| 1000Hz shm                   |     2345 |      0 |     0.0300 MB/s |    0.0009ms |    0.0225ms |    0.0299ms |
| 2000Hz shm                   |     4417 |      0 |     0.0565 MB/s |    0.0008ms |    0.0136ms |    0.0268ms |
| 5000Hz shm                   |     9367 |      0 |     0.1199 MB/s |    0.0007ms |    0.0115ms |    0.0428ms |
| 10000Hz shm                  |    15062 |      0 |     0.1928 MB/s |    0.0006ms |    0.0093ms |    0.0225ms |
| 500Hz udp                    |     1209 |      0 |     0.0155 MB/s |    0.0094ms |    0.0156ms |    0.0701ms |
| 1000Hz udp                   |     2338 |      0 |     0.0299 MB/s |    0.0104ms |    0.0184ms |    0.0607ms |
| 2000Hz udp                   |     4418 |      0 |     0.0566 MB/s |    0.0078ms |    0.0126ms |    0.0563ms |
| 5000Hz udp                   |     9406 |      0 |     0.1204 MB/s |    0.0079ms |    0.0137ms |    0.0571ms |
| 10000Hz udp                  |    15001 |      0 |     0.1920 MB/s |    0.0084ms |    0.0154ms |    0.0564ms |

## 2. LaserScan rate sweep (2000-point-equivalent payload, ~8KB)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 10Hz shm                     |       25 |      0 |     0.0806 MB/s |    0.0341ms |    0.0498ms |    0.0498ms |
| 20Hz shm                     |       50 |      0 |     0.1613 MB/s |    0.0316ms |    0.0505ms |    0.0505ms |
| 40Hz shm                     |      100 |      0 |     0.3226 MB/s |    0.0253ms |    0.0501ms |    0.0501ms |
| 60Hz shm                     |      150 |      0 |     0.4838 MB/s |    0.0223ms |    0.0496ms |    0.0579ms |
| 10Hz udp                     |       25 |      0 |     0.0806 MB/s |    0.0921ms |    0.1290ms |    0.1290ms |
| 20Hz udp                     |       50 |      0 |     0.1613 MB/s |    0.0834ms |    0.1297ms |    0.1297ms |
| 40Hz udp                     |      100 |      0 |     0.3226 MB/s |    0.0686ms |    0.1191ms |    0.1191ms |
| 60Hz udp                     |      150 |      0 |     0.4838 MB/s |    0.0622ms |    0.0947ms |    0.1189ms |

## 3. Unpaced firehose (worst case, no publisher pacing at all)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 64KB FIFO ring, shm          |   266121 |      0 |  8720.2529 MB/s |    0.0104ms |    0.0291ms |    0.6818ms |


## CPU core affinity comparison

Tests whether pinning the publisher and subscriber to dedicated CPU
cores (sched_setaffinity) reduces scheduling-contention tail latency,
compared to leaving scheduling up to the OS default. On a single-core
machine this is structurally a no-op (nothing to isolate from).
```
nproc=4

=== Unpinned (OS default scheduling) ===
unpinned                                 sent=  299893 dispatched=  299893 drops=     0 mean=  0.0095ms p50=  0.0084ms p99=  0.0283ms max=   0.6772ms
unpinned                                 sent=  299751 dispatched=  299751 drops=     0 mean=  0.0093ms p50=  0.0083ms p99=  0.0278ms max=   0.6344ms
unpinned                                 sent=  297155 dispatched=  297155 drops=     0 mean=  0.0096ms p50=  0.0084ms p99=  0.0284ms max=   0.6902ms

=== Pinned: publisher->CPU0, subscriber->CPU1 ===
pinned                                   sent=  339759 dispatched=  339759 drops=     0 mean=  0.0130ms p50=  0.0082ms p99=  0.0509ms max=   0.9380ms
pinned                                   sent= 1073567 dispatched=       0 drops=     0 mean=  0.0000ms p50=  0.0000ms p99=  0.0000ms max=   0.0000ms
pinned                                   sent=  372688 dispatched=  372688 drops=     0 mean=  0.0138ms p50=  0.0077ms p99=  0.0525ms max=   0.9237ms
```
