# commsys C++ benchmark report

Generated: 2026-08-09 07:00:11 UTC

## Hardware
```
vCPUs: 4
               total        used        free      shared  buff/cache   available
Mem:            15Gi       1.1Gi        10Gi        47Mi       4.8Gi        14Gi
Swap:          3.0Gi          0B       3.0Gi
Linux runnervmvrwv9 6.17.0-1020-azure #20~24.04.1-Ubuntu SMP Fri Jun 19 20:09:14 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
```

## Unit tests (ctest / Catch2)
```
Test project /home/runner/work/cc-code/cc-code/commsys/cpp/build
    Start 1: commsys_tests
1/1 Test #1: commsys_tests ....................   Passed   27.38 sec

100% tests passed, 0 tests failed out of 1

Total Test time (real) =  27.38 sec
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
[keep_latest] sent=259487 (unpaced firehose)
[keep_latest] dispatched=375
[keep_latest] mean=0.0182ms p50=0.0179ms p99=0.0348ms max=0.0470ms
-- test_ring_stress --
[fifo ring] sent=469591 (unpaced firehose)
[fifo ring] dispatched=469591 drops=0
[fifo ring] mean=0.0108ms p50=0.0082ms p99=0.0295ms max=1.0455ms
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
| 500Hz shm                    |     1214 |      0 |     0.0155 MB/s |    0.0005ms |    0.0089ms |    0.0219ms |
| 1000Hz shm                   |     2361 |      0 |     0.0302 MB/s |    0.0005ms |    0.0076ms |    0.0223ms |
| 2000Hz shm                   |     4472 |      0 |     0.0572 MB/s |    0.0005ms |    0.0054ms |    0.0218ms |
| 5000Hz shm                   |     9699 |      0 |     0.1241 MB/s |    0.0007ms |    0.0051ms |    0.0232ms |
| 10000Hz shm                  |    15834 |      0 |     0.2027 MB/s |    0.0006ms |    0.0048ms |    0.0275ms |
| 500Hz udp                    |     1214 |      0 |     0.0155 MB/s |    0.0044ms |    0.0076ms |    0.0673ms |
| 1000Hz udp                   |     2361 |      0 |     0.0302 MB/s |    0.0040ms |    0.0060ms |    0.0625ms |
| 2000Hz udp                   |     4476 |      0 |     0.0573 MB/s |    0.0039ms |    0.0067ms |    0.0694ms |
| 5000Hz udp                   |     9668 |      0 |     0.1238 MB/s |    0.0040ms |    0.0051ms |    0.0688ms |
| 10000Hz udp                  |    15761 |      0 |     0.2017 MB/s |    0.0037ms |    0.0052ms |    0.0546ms |

## 2. LaserScan rate sweep (2000-point-equivalent payload, ~8KB)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 10Hz shm                     |       25 |      0 |     0.0806 MB/s |    0.0290ms |    0.0454ms |    0.0454ms |
| 20Hz shm                     |       50 |      0 |     0.1613 MB/s |    0.0181ms |    0.0518ms |    0.0518ms |
| 40Hz shm                     |      100 |      0 |     0.3226 MB/s |    0.0163ms |    0.0512ms |    0.0512ms |
| 60Hz shm                     |      150 |      0 |     0.4838 MB/s |    0.0135ms |    0.0465ms |    0.0536ms |
| 10Hz udp                     |       25 |      0 |     0.0806 MB/s |    0.0521ms |    0.1050ms |    0.1050ms |
| 20Hz udp                     |       50 |      0 |     0.1613 MB/s |    0.0482ms |    0.1086ms |    0.1086ms |
| 40Hz udp                     |      100 |      0 |     0.3226 MB/s |    0.0347ms |    0.1223ms |    0.1223ms |
| 60Hz udp                     |      150 |      0 |     0.4838 MB/s |    0.0360ms |    0.0802ms |    0.1147ms |

## 3. Unpaced firehose (worst case, no publisher pacing at all)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 64KB FIFO ring, shm          |   472344 |      0 | 15477.7682 MB/s |    0.0108ms |    0.0290ms |    1.1846ms |


## CPU core affinity comparison

Tests whether pinning the publisher and subscriber to dedicated CPU
cores (sched_setaffinity) reduces scheduling-contention tail latency,
compared to leaving scheduling up to the OS default. On a single-core
machine this is structurally a no-op (nothing to isolate from).
```
nproc=4

=== Unpinned (OS default scheduling) ===
unpinned                                 sent=  439117 dispatched=  439117 drops=     0 mean=  0.0095ms p50=  0.0084ms p99=  0.0244ms max=   0.6187ms
unpinned                                 sent=  475113 dispatched=  475113 drops=     0 mean=  0.0107ms p50=  0.0082ms p99=  0.0660ms max=   0.5896ms
unpinned                                 sent=  467035 dispatched=  467035 drops=     0 mean=  0.0104ms p50=  0.0082ms p99=  0.0314ms max=   0.6274ms

=== Pinned: publisher->CPU0, subscriber->CPU1 ===
pinned                                   sent=  367792 dispatched=  367792 drops=     0 mean=  0.0093ms p50=  0.0080ms p99=  0.0252ms max=   0.9114ms
pinned                                   sent=  377160 dispatched=  377160 drops=     0 mean=  0.0096ms p50=  0.0080ms p99=  0.0253ms max=   0.9567ms
pinned                                   sent=  376133 dispatched=  376133 drops=     0 mean=  0.0094ms p50=  0.0080ms p99=  0.0251ms max=   0.9125ms
```
