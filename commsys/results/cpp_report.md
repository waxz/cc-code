# commsys C++ benchmark report

Generated: 2026-08-09 09:35:08 UTC

## Hardware
```
vCPUs: 4
               total        used        free      shared  buff/cache   available
Mem:            15Gi       1.0Gi        11Gi        45Mi       3.2Gi        14Gi
Swap:          3.0Gi          0B       3.0Gi
Linux runnervmvrwv9 6.17.0-1020-azure #20~24.04.1-Ubuntu SMP Fri Jun 19 20:09:14 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
```

## Unit tests (ctest / Catch2)
```
Test project /home/runner/work/cc-code/cc-code/commsys/cpp/build
    Start 1: commsys_tests
1/1 Test #1: commsys_tests ....................   Passed   27.38 sec

100% tests passed, 0 tests failed out of 1

Total Test time (real) =  27.45 sec
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
[keep_latest] sent=380268 (unpaced firehose)
[keep_latest] dispatched=377574
[keep_latest] mean=0.0064ms p50=0.0063ms p99=0.0087ms max=0.1264ms
-- test_ring_stress --
[fifo ring] sent=558888 (unpaced firehose)
[fifo ring] dispatched=558888 drops=0
[fifo ring] mean=0.0072ms p50=0.0053ms p99=0.0260ms max=0.6801ms
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
| 500Hz shm                    |     1208 |      0 |     0.0155 MB/s |    0.0008ms |    0.0104ms |    0.0235ms |
| 1000Hz shm                   |     2347 |      0 |     0.0300 MB/s |    0.0007ms |    0.0088ms |    0.0170ms |
| 2000Hz shm                   |     4410 |      0 |     0.0564 MB/s |    0.0006ms |    0.0089ms |    0.0217ms |
| 5000Hz shm                   |     9389 |      0 |     0.1202 MB/s |    0.0006ms |    0.0080ms |    0.0202ms |
| 10000Hz shm                  |    14903 |      0 |     0.1908 MB/s |    0.0009ms |    0.0089ms |    0.1890ms |
| 500Hz udp                    |     1207 |      0 |     0.0154 MB/s |    0.0101ms |    0.0185ms |    0.0684ms |
| 1000Hz udp                   |     2342 |      0 |     0.0300 MB/s |    0.0088ms |    0.0155ms |    0.0380ms |
| 2000Hz udp                   |     4396 |      0 |     0.0563 MB/s |    0.0095ms |    0.0162ms |    0.0477ms |
| 5000Hz udp                   |     9338 |      0 |     0.1195 MB/s |    0.0088ms |    0.0154ms |    0.0485ms |
| 10000Hz udp                  |    14944 |      0 |     0.1913 MB/s |    0.0086ms |    0.0147ms |    0.0359ms |

## 2. LaserScan rate sweep (2000-point-equivalent payload, ~8KB)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 10Hz shm                     |       25 |      0 |     0.0806 MB/s |    0.0192ms |    0.0274ms |    0.0274ms |
| 20Hz shm                     |       50 |      0 |     0.1613 MB/s |    0.0183ms |    0.0406ms |    0.0406ms |
| 40Hz shm                     |      100 |      0 |     0.3226 MB/s |    0.0183ms |    0.0557ms |    0.0557ms |
| 60Hz shm                     |      150 |      0 |     0.4838 MB/s |    0.0181ms |    0.0511ms |    0.0514ms |
| 10Hz udp                     |       25 |      0 |     0.0806 MB/s |    0.0710ms |    0.0966ms |    0.0966ms |
| 20Hz udp                     |       50 |      0 |     0.1613 MB/s |    0.0662ms |    0.1088ms |    0.1088ms |
| 40Hz udp                     |      100 |      0 |     0.3226 MB/s |    0.0594ms |    0.1183ms |    0.1183ms |
| 60Hz udp                     |      150 |      0 |     0.4838 MB/s |    0.0555ms |    0.0729ms |    0.1118ms |

## 3. Unpaced firehose (worst case, no publisher pacing at all)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 64KB FIFO ring, shm          |   539006 |      0 | 17662.1486 MB/s |    0.0076ms |    0.0265ms |    0.6831ms |


## CPU core affinity comparison

Tests whether pinning the publisher and subscriber to dedicated CPU
cores (sched_setaffinity) reduces scheduling-contention tail latency,
compared to leaving scheduling up to the OS default. On a single-core
machine this is structurally a no-op (nothing to isolate from).
```
nproc=4

=== Unpinned (OS default scheduling) ===
unpinned                                 sent=  486309 dispatched=  486309 drops=     0 mean=  0.0075ms p50=  0.0058ms p99=  0.0265ms max=   0.6875ms
unpinned                                 sent=  530668 dispatched=  530668 drops=     0 mean=  0.0068ms p50=  0.0054ms p99=  0.0260ms max=   0.7155ms
unpinned                                 sent=  542244 dispatched=  542244 drops=     0 mean=  0.0076ms p50=  0.0054ms p99=  0.0263ms max=   0.7371ms

=== Pinned: publisher->CPU0, subscriber->CPU1 ===
pinned                                   sent=  358755 dispatched=  358755 drops=     0 mean=  0.0138ms p50=  0.0080ms p99=  0.0527ms max=   0.9861ms
pinned                                   sent=  355372 dispatched=  355372 drops=     0 mean=  0.0134ms p50=  0.0080ms p99=  0.0511ms max=   0.9457ms
pinned                                   sent=  344393 dispatched=  344393 drops=     0 mean=  0.0133ms p50=  0.0082ms p99=  0.0511ms max=   0.9580ms
```
