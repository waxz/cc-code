# commsys C++ benchmark report

Generated: 2026-08-07 21:17:52 UTC

## Hardware
```
vCPUs: 4
               total        used        free      shared  buff/cache   available
Mem:            15Gi       992Mi        11Gi        47Mi       3.2Gi        14Gi
Swap:          3.0Gi          0B       3.0Gi
Linux runnervmvrwv9 6.17.0-1020-azure #20~24.04.1-Ubuntu SMP Fri Jun 19 20:09:14 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
```

## Unit tests (ctest / Catch2)
```
Test project /home/runner/work/cc-code/cc-code/commsys/cpp/build
    Start 1: commsys_tests
1/1 Test #1: commsys_tests ....................   Passed   27.38 sec

100% tests passed, 0 tests failed out of 1

Total Test time (real) =  27.46 sec
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
[keep_latest] sent=322242 (unpaced firehose)
[keep_latest] dispatched=320364
[keep_latest] mean=0.0073ms p50=0.0071ms p99=0.0098ms max=0.0684ms
-- test_ring_stress --
[fifo ring] sent=492250 (unpaced firehose)
[fifo ring] dispatched=492250 drops=0
[fifo ring] mean=0.0080ms p50=0.0057ms p99=0.0344ms max=1.3921ms
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
| 500Hz shm                    |     1209 |      0 |     0.0155 MB/s |    0.0008ms |    0.0167ms |    0.0580ms |
| 1000Hz shm                   |     2345 |      0 |     0.0300 MB/s |    0.0007ms |    0.0116ms |    0.0207ms |
| 2000Hz shm                   |     4427 |      0 |     0.0567 MB/s |    0.0006ms |    0.0080ms |    0.0236ms |
| 5000Hz shm                   |     9408 |      0 |     0.1204 MB/s |    0.0006ms |    0.0079ms |    0.0164ms |
| 10000Hz shm                  |    15161 |      0 |     0.1941 MB/s |    0.0006ms |    0.0069ms |    0.0219ms |
| 500Hz udp                    |     1209 |      0 |     0.0155 MB/s |    0.0095ms |    0.0180ms |    0.0638ms |
| 1000Hz udp                   |     2344 |      0 |     0.0300 MB/s |    0.0084ms |    0.0140ms |    0.0625ms |
| 2000Hz udp                   |     4416 |      0 |     0.0565 MB/s |    0.0081ms |    0.0130ms |    0.0644ms |
| 5000Hz udp                   |     9401 |      0 |     0.1203 MB/s |    0.0079ms |    0.0136ms |    0.0631ms |
| 10000Hz udp                  |    15035 |      0 |     0.1924 MB/s |    0.0081ms |    0.0131ms |    0.0611ms |

## 2. LaserScan rate sweep (2000-point-equivalent payload, ~8KB)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 10Hz shm                     |       25 |      0 |     0.0806 MB/s |    0.0266ms |    0.0652ms |    0.0652ms |
| 20Hz shm                     |       50 |      0 |     0.1613 MB/s |    0.0216ms |    0.0619ms |    0.0619ms |
| 40Hz shm                     |      100 |      0 |     0.3226 MB/s |    0.0184ms |    0.0460ms |    0.0460ms |
| 60Hz shm                     |      150 |      0 |     0.4838 MB/s |    0.0174ms |    0.0254ms |    0.0431ms |
| 10Hz udp                     |       25 |      0 |     0.0806 MB/s |    0.0744ms |    0.1095ms |    0.1095ms |
| 20Hz udp                     |       50 |      0 |     0.1613 MB/s |    0.0701ms |    0.1066ms |    0.1066ms |
| 40Hz udp                     |      100 |      0 |     0.3226 MB/s |    0.0561ms |    0.1124ms |    0.1124ms |
| 60Hz udp                     |      150 |      0 |     0.4838 MB/s |    0.0556ms |    0.0825ms |    0.1022ms |

## 3. Unpaced firehose (worst case, no publisher pacing at all)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 64KB FIFO ring, shm          |   449412 |      0 | 14726.3324 MB/s |    0.0076ms |    0.0267ms |    0.6155ms |


## CPU core affinity comparison

Tests whether pinning the publisher and subscriber to dedicated CPU
cores (sched_setaffinity) reduces scheduling-contention tail latency,
compared to leaving scheduling up to the OS default. On a single-core
machine this is structurally a no-op (nothing to isolate from).
```
nproc=4

=== Unpinned (OS default scheduling) ===
unpinned                                 sent=  450096 dispatched=  450096 drops=     0 mean=  0.0076ms p50=  0.0061ms p99=  0.0268ms max=   0.6859ms
unpinned                                 sent=  553825 dispatched=  553825 drops=     0 mean=  0.0066ms p50=  0.0052ms p99=  0.0258ms max=   0.7045ms
unpinned                                 sent=  553653 dispatched=  553653 drops=     0 mean=  0.0074ms p50=  0.0053ms p99=  0.0262ms max=   0.6869ms

=== Pinned: publisher->CPU0, subscriber->CPU1 ===
pinned                                   sent=  355635 dispatched=  355635 drops=     0 mean=  0.0132ms p50=  0.0080ms p99=  0.0520ms max=   0.8967ms
pinned                                   sent=  374745 dispatched=  374745 drops=     0 mean=  0.0140ms p50=  0.0078ms p99=  0.0541ms max=   0.9416ms
pinned                                   sent=  342755 dispatched=  342755 drops=     0 mean=  0.0124ms p50=  0.0078ms p99=  0.0520ms max=   0.9072ms
```
