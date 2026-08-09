# commsys C++ benchmark report

Generated: 2026-08-09 13:26:58 UTC

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

Total Test time (real) =  27.44 sec
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
[keep_latest] sent=373444 (unpaced firehose)
[keep_latest] dispatched=362938
[keep_latest] mean=0.0065ms p50=0.0064ms p99=0.0093ms max=0.0418ms
-- test_ring_stress --
[fifo ring] sent=299261 (unpaced firehose)
[fifo ring] dispatched=299261 drops=0
[fifo ring] mean=0.0097ms p50=0.0085ms p99=0.0282ms max=1.0512ms
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
| 500Hz shm                    |     1209 |      0 |     0.0155 MB/s |    0.0009ms |    0.0229ms |    0.0305ms |
| 1000Hz shm                   |     2343 |      0 |     0.0300 MB/s |    0.0008ms |    0.0137ms |    0.0376ms |
| 2000Hz shm                   |     4413 |      0 |     0.0565 MB/s |    0.0007ms |    0.0109ms |    0.0272ms |
| 5000Hz shm                   |     9396 |      0 |     0.1203 MB/s |    0.0007ms |    0.0086ms |    0.0720ms |
| 10000Hz shm                  |    15082 |      0 |     0.1930 MB/s |    0.0006ms |    0.0086ms |    0.0300ms |
| 500Hz udp                    |     1208 |      0 |     0.0155 MB/s |    0.0096ms |    0.0192ms |    0.0649ms |
| 1000Hz udp                   |     2345 |      0 |     0.0300 MB/s |    0.0084ms |    0.0156ms |    0.0562ms |
| 2000Hz udp                   |     4409 |      0 |     0.0564 MB/s |    0.0087ms |    0.0152ms |    0.0594ms |
| 5000Hz udp                   |     9322 |      0 |     0.1193 MB/s |    0.0093ms |    0.0166ms |    0.0708ms |
| 10000Hz udp                  |    14943 |      0 |     0.1913 MB/s |    0.0089ms |    0.0152ms |    0.0537ms |

## 2. LaserScan rate sweep (2000-point-equivalent payload, ~8KB)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 10Hz shm                     |       25 |      0 |     0.0806 MB/s |    0.0196ms |    0.0328ms |    0.0328ms |
| 20Hz shm                     |       50 |      0 |     0.1613 MB/s |    0.0258ms |    0.0501ms |    0.0501ms |
| 40Hz shm                     |      100 |      0 |     0.3226 MB/s |    0.0197ms |    0.0503ms |    0.0503ms |
| 60Hz shm                     |      150 |      0 |     0.4838 MB/s |    0.0189ms |    0.0326ms |    0.0565ms |
| 10Hz udp                     |       25 |      0 |     0.0806 MB/s |    0.0583ms |    0.1111ms |    0.1111ms |
| 20Hz udp                     |       50 |      0 |     0.1613 MB/s |    0.0560ms |    0.0973ms |    0.0973ms |
| 40Hz udp                     |      100 |      0 |     0.3226 MB/s |    0.0543ms |    0.1014ms |    0.1014ms |
| 60Hz udp                     |      150 |      0 |     0.4838 MB/s |    0.0545ms |    0.0695ms |    0.1123ms |

## 3. Unpaced firehose (worst case, no publisher pacing at all)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 64KB FIFO ring, shm          |   298008 |      0 |  9765.1261 MB/s |    0.0095ms |    0.0287ms |    0.6149ms |


## CPU core affinity comparison

Tests whether pinning the publisher and subscriber to dedicated CPU
cores (sched_setaffinity) reduces scheduling-contention tail latency,
compared to leaving scheduling up to the OS default. On a single-core
machine this is structurally a no-op (nothing to isolate from).
```
nproc=4

=== Unpinned (OS default scheduling) ===
unpinned                                 sent=  294707 dispatched=  294707 drops=     0 mean=  0.0100ms p50=  0.0086ms p99=  0.0285ms max=   1.1460ms
unpinned                                 sent=  314671 dispatched=  314671 drops=     0 mean=  0.0095ms p50=  0.0081ms p99=  0.0276ms max=   1.0926ms
unpinned                                 sent=  308089 dispatched=  308089 drops=     0 mean=  0.0096ms p50=  0.0083ms p99=  0.0283ms max=   0.8986ms

=== Pinned: publisher->CPU0, subscriber->CPU1 ===
pinned                                   sent=  377696 dispatched=  377696 drops=     0 mean=  0.0150ms p50=  0.0077ms p99=  0.0558ms max=   1.2804ms
pinned                                   sent=  382775 dispatched=  382775 drops=     0 mean=  0.0150ms p50=  0.0076ms p99=  0.0570ms max=   1.2883ms
pinned                                   sent=  379853 dispatched=  379853 drops=     0 mean=  0.0151ms p50=  0.0077ms p99=  0.0563ms max=   1.2846ms
```
