# commsys C++ benchmark report

Generated: 2026-08-09 15:53:23 UTC

## Hardware
```
vCPUs: 4
               total        used        free      shared  buff/cache   available
Mem:            15Gi       1.0Gi        11Gi        46Mi       3.2Gi        14Gi
Swap:          3.0Gi          0B       3.0Gi
Linux runnervmvrwv9 6.17.0-1020-azure #20~24.04.1-Ubuntu SMP Fri Jun 19 20:09:14 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
```

## Unit tests (ctest / Catch2)
```
Test project /home/runner/work/cc-code/cc-code/commsys/cpp/build
    Start 1: commsys_tests
1/1 Test #1: commsys_tests ....................   Passed   27.38 sec

100% tests passed, 0 tests failed out of 1

Total Test time (real) =  27.51 sec
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
[keep_latest] sent=361559 (unpaced firehose)
[keep_latest] dispatched=360022
[keep_latest] mean=0.0066ms p50=0.0066ms p99=0.0095ms max=0.0520ms
-- test_ring_stress --
[fifo ring] sent=465426 (unpaced firehose)
[fifo ring] dispatched=465426 drops=0
[fifo ring] mean=0.0077ms p50=0.0059ms p99=0.0271ms max=0.8551ms
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
| 500Hz shm                    |     1208 |      0 |     0.0155 MB/s |    0.0010ms |    0.0239ms |    0.0368ms |
| 1000Hz shm                   |     2347 |      0 |     0.0300 MB/s |    0.0008ms |    0.0178ms |    0.0346ms |
| 2000Hz shm                   |     4417 |      0 |     0.0565 MB/s |    0.0007ms |    0.0141ms |    0.0368ms |
| 5000Hz shm                   |     9442 |      0 |     0.1209 MB/s |    0.0006ms |    0.0090ms |    0.0376ms |
| 10000Hz shm                  |    15079 |      0 |     0.1930 MB/s |    0.0007ms |    0.0084ms |    0.0913ms |
| 500Hz udp                    |     1209 |      0 |     0.0155 MB/s |    0.0096ms |    0.0166ms |    0.0616ms |
| 1000Hz udp                   |     2340 |      0 |     0.0300 MB/s |    0.0094ms |    0.0164ms |    0.0585ms |
| 2000Hz udp                   |     4391 |      0 |     0.0562 MB/s |    0.0101ms |    0.0232ms |    0.0564ms |
| 5000Hz udp                   |     9397 |      0 |     0.1203 MB/s |    0.0080ms |    0.0133ms |    0.0560ms |
| 10000Hz udp                  |    15031 |      0 |     0.1924 MB/s |    0.0082ms |    0.0144ms |    0.0551ms |

## 2. LaserScan rate sweep (2000-point-equivalent payload, ~8KB)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 10Hz shm                     |       25 |      0 |     0.0806 MB/s |    0.0323ms |    0.0479ms |    0.0479ms |
| 20Hz shm                     |       50 |      0 |     0.1613 MB/s |    0.0280ms |    0.0530ms |    0.0530ms |
| 40Hz shm                     |      100 |      0 |     0.3226 MB/s |    0.0231ms |    0.0509ms |    0.0509ms |
| 60Hz shm                     |      150 |      0 |     0.4838 MB/s |    0.0205ms |    0.0383ms |    0.0490ms |
| 10Hz udp                     |       25 |      0 |     0.0806 MB/s |    0.0835ms |    0.1128ms |    0.1128ms |
| 20Hz udp                     |       50 |      0 |     0.1613 MB/s |    0.0760ms |    0.1067ms |    0.1067ms |
| 40Hz udp                     |      100 |      0 |     0.3226 MB/s |    0.0657ms |    0.1216ms |    0.1216ms |
| 60Hz udp                     |      150 |      0 |     0.4838 MB/s |    0.0606ms |    0.0807ms |    0.1168ms |

## 3. Unpaced firehose (worst case, no publisher pacing at all)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 64KB FIFO ring, shm          |   436805 |      0 | 14313.2262 MB/s |    0.0077ms |    0.0268ms |    0.6239ms |


## CPU core affinity comparison

Tests whether pinning the publisher and subscriber to dedicated CPU
cores (sched_setaffinity) reduces scheduling-contention tail latency,
compared to leaving scheduling up to the OS default. On a single-core
machine this is structurally a no-op (nothing to isolate from).
```
nproc=4

=== Unpinned (OS default scheduling) ===
unpinned                                 sent=  499318 dispatched=  499318 drops=     0 mean=  0.0074ms p50=  0.0057ms p99=  0.0266ms max=   0.6681ms
unpinned                                 sent=  544522 dispatched=  544522 drops=     0 mean=  0.0068ms p50=  0.0053ms p99=  0.0259ms max=   0.6836ms
unpinned                                 sent=  482389 dispatched=  482389 drops=     0 mean=  0.0074ms p50=  0.0058ms p99=  0.0265ms max=   0.6411ms

=== Pinned: publisher->CPU0, subscriber->CPU1 ===
pinned                                   sent= 1073959 dispatched=       0 drops=     0 mean=  0.0000ms p50=  0.0000ms p99=  0.0000ms max=   0.0000ms
pinned                                   sent=  354721 dispatched=  354721 drops=     0 mean=  0.0139ms p50=  0.0081ms p99=  0.0530ms max=   1.0024ms
pinned                                   sent=  345965 dispatched=  345965 drops=     0 mean=  0.0138ms p50=  0.0083ms p99=  0.0528ms max=   0.9455ms
```
