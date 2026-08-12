# commsys C++ benchmark report

Generated: 2026-08-12 14:50:06 UTC

## Hardware
```
vCPUs: 4
               total        used        free      shared  buff/cache   available
Mem:            15Gi       1.0Gi        10Gi        47Mi       4.8Gi        14Gi
Swap:          3.0Gi          0B       3.0Gi
Linux runnervmvrwv9 6.17.0-1020-azure #20~24.04.1-Ubuntu SMP Fri Jun 19 20:09:14 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
```

## Unit tests (ctest / Catch2)
```
Test project /home/runner/work/cc-code/cc-code/commsys/cpp/build
    Start 1: commsys_tests
1/1 Test #1: commsys_tests ....................   Passed   34.38 sec

100% tests passed, 0 tests failed out of 1

Total Test time (real) =  34.38 sec
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
[keep_latest] sent=211010 (unpaced firehose)
[keep_latest] dispatched=202633
[keep_latest] mean=0.0106ms p50=0.0105ms p99=0.0163ms max=0.0685ms
-- test_ring_stress --
[fifo ring] sent=536388 (unpaced firehose)
[fifo ring] dispatched=536388 drops=0
[fifo ring] mean=0.0062ms p50=0.0054ms p99=0.0207ms max=0.5876ms
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
| 500Hz shm                    |     1207 |      0 |     0.0154 MB/s |    0.0012ms |    0.0264ms |    0.0412ms |
| 1000Hz shm                   |     2359 |      0 |     0.0302 MB/s |    0.0009ms |    0.0176ms |    0.0469ms |
| 2000Hz shm                   |     4466 |      0 |     0.0572 MB/s |    0.0008ms |    0.0130ms |    0.0286ms |
| 5000Hz shm                   |     9660 |      0 |     0.1236 MB/s |    0.0007ms |    0.0089ms |    0.0289ms |
| 10000Hz shm                  |    15714 |      0 |     0.2011 MB/s |    0.0007ms |    0.0074ms |    0.0320ms |
| 500Hz udp                    |     1204 |      0 |     0.0154 MB/s |    0.0144ms |    0.0226ms |    0.0804ms |
| 1000Hz udp                   |     2360 |      0 |     0.0302 MB/s |    0.0067ms |    0.0115ms |    0.0735ms |
| 2000Hz udp                   |     4462 |      0 |     0.0571 MB/s |    0.0070ms |    0.0146ms |    0.0719ms |
| 5000Hz udp                   |     9581 |      0 |     0.1226 MB/s |    0.0059ms |    0.0102ms |    0.0737ms |
| 10000Hz udp                  |    15712 |      0 |     0.2011 MB/s |    0.0058ms |    0.0081ms |    0.0856ms |

## 2. LaserScan rate sweep (2000-point-equivalent payload, ~8KB)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 10Hz shm                     |       25 |      0 |     0.0806 MB/s |    0.0364ms |    0.0741ms |    0.0741ms |
| 20Hz shm                     |       50 |      0 |     0.1613 MB/s |    0.0270ms |    0.0495ms |    0.0495ms |
| 40Hz shm                     |      100 |      0 |     0.3226 MB/s |    0.0208ms |    0.0529ms |    0.0529ms |
| 60Hz shm                     |      150 |      0 |     0.4838 MB/s |    0.0189ms |    0.0388ms |    0.0515ms |
| 10Hz udp                     |       25 |      0 |     0.0806 MB/s |    0.0766ms |    0.1067ms |    0.1067ms |
| 20Hz udp                     |       50 |      0 |     0.1613 MB/s |    0.0661ms |    0.1142ms |    0.1142ms |
| 40Hz udp                     |      100 |      0 |     0.3226 MB/s |    0.0533ms |    0.1198ms |    0.1198ms |
| 60Hz udp                     |      150 |      0 |     0.4838 MB/s |    0.0480ms |    0.0711ms |    0.1167ms |

## 3. Unpaced firehose (worst case, no publisher pacing at all)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 64KB FIFO ring, shm          |   420039 |      0 | 13763.8380 MB/s |    0.0075ms |    0.0230ms |    0.8996ms |


## CPU core affinity comparison

Tests whether pinning the publisher and subscriber to dedicated CPU
cores (sched_setaffinity) reduces scheduling-contention tail latency,
compared to leaving scheduling up to the OS default. On a single-core
machine this is structurally a no-op (nothing to isolate from).
```
nproc=4

=== Unpinned (OS default scheduling) ===
unpinned                                 sent=  410252 dispatched=  410252 drops=     0 mean=  0.0072ms p50=  0.0066ms p99=  0.0209ms max=   0.5263ms
unpinned                                 sent=  358260 dispatched=  358260 drops=     0 mean=  0.0079ms p50=  0.0079ms p99=  0.0219ms max=   0.5480ms
unpinned                                 sent=  605269 dispatched=  605269 drops=     0 mean=  0.0059ms p50=  0.0050ms p99=  0.0218ms max=   0.5323ms

=== Pinned: publisher->CPU0, subscriber->CPU1 ===
pinned                                   sent= 1062741 dispatched=       0 drops=     0 mean=  0.0000ms p50=  0.0000ms p99=  0.0000ms max=   0.0000ms
pinned                                   sent=  406057 dispatched=  406057 drops=     0 mean=  0.0090ms p50=  0.0070ms p99=  0.0379ms max=   0.7980ms
pinned                                   sent=  432552 dispatched=  432552 drops=     0 mean=  0.0098ms p50=  0.0070ms p99=  0.0388ms max=   0.8237ms
```
