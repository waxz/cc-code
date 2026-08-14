# commsys C++ benchmark report

Generated: 2026-08-14 16:42:09 UTC

## Hardware
```
vCPUs: 4
               total        used        free      shared  buff/cache   available
Mem:            15Gi       1.0Gi        10Gi        47Mi       4.7Gi        14Gi
Swap:          3.0Gi          0B       3.0Gi
Linux runnervmzvulz 6.17.0-1022-azure #22-Ubuntu SMP Mon Jul 27 17:24:03 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
```

## Unit tests (ctest / Catch2)
```
Test project /home/runner/work/cc-code/cc-code/commsys/cpp/build
    Start 1: commsys_tests
1/1 Test #1: commsys_tests ....................   Passed   34.38 sec

100% tests passed, 0 tests failed out of 1

Total Test time (real) =  34.39 sec
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
[keep_latest] sent=199585 (unpaced firehose)
[keep_latest] dispatched=198087
[keep_latest] mean=0.0111ms p50=0.0111ms p99=0.0153ms max=0.1663ms
-- test_ring_stress --
[fifo ring] sent=309494 (unpaced firehose)
[fifo ring] dispatched=309494 drops=0
[fifo ring] mean=0.0086ms p50=0.0082ms p99=0.0206ms max=0.5230ms
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
| 500Hz shm                    |     1204 |      0 |     0.0154 MB/s |    0.0013ms |    0.0268ms |    0.0367ms |
| 1000Hz shm                   |     2360 |      0 |     0.0302 MB/s |    0.0010ms |    0.0220ms |    0.0374ms |
| 2000Hz shm                   |     4468 |      0 |     0.0572 MB/s |    0.0008ms |    0.0148ms |    0.0348ms |
| 5000Hz shm                   |     9673 |      0 |     0.1238 MB/s |    0.0007ms |    0.0101ms |    0.0253ms |
| 10000Hz shm                  |    15770 |      0 |     0.2019 MB/s |    0.0007ms |    0.0078ms |    0.0283ms |
| 500Hz udp                    |     1203 |      0 |     0.0154 MB/s |    0.0149ms |    0.0301ms |    0.0678ms |
| 1000Hz udp                   |     2360 |      0 |     0.0302 MB/s |    0.0069ms |    0.0143ms |    0.0627ms |
| 2000Hz udp                   |     4468 |      0 |     0.0572 MB/s |    0.0066ms |    0.0117ms |    0.0659ms |
| 5000Hz udp                   |     9643 |      0 |     0.1234 MB/s |    0.0062ms |    0.0099ms |    0.0626ms |
| 10000Hz udp                  |    15740 |      0 |     0.2015 MB/s |    0.0059ms |    0.0087ms |    0.0582ms |

## 2. LaserScan rate sweep (2000-point-equivalent payload, ~8KB)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 10Hz shm                     |       25 |      0 |     0.0806 MB/s |    0.0331ms |    0.0412ms |    0.0412ms |
| 20Hz shm                     |       50 |      0 |     0.1613 MB/s |    0.0280ms |    0.0563ms |    0.0563ms |
| 40Hz shm                     |      100 |      0 |     0.3226 MB/s |    0.0212ms |    0.0565ms |    0.0565ms |
| 60Hz shm                     |      150 |      0 |     0.4838 MB/s |    0.0187ms |    0.0341ms |    0.0743ms |
| 10Hz udp                     |       25 |      0 |     0.0806 MB/s |    0.0759ms |    0.1088ms |    0.1088ms |
| 20Hz udp                     |       50 |      0 |     0.1613 MB/s |    0.0657ms |    0.1188ms |    0.1188ms |
| 40Hz udp                     |      100 |      0 |     0.3226 MB/s |    0.0554ms |    0.1088ms |    0.1088ms |
| 60Hz udp                     |      150 |      0 |     0.4838 MB/s |    0.0488ms |    0.0745ms |    0.1096ms |

## 3. Unpaced firehose (worst case, no publisher pacing at all)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 64KB FIFO ring, shm          |   280933 |      0 |  9205.6125 MB/s |    0.0093ms |    0.0223ms |    0.5737ms |


## CPU core affinity comparison

Tests whether pinning the publisher and subscriber to dedicated CPU
cores (sched_setaffinity) reduces scheduling-contention tail latency,
compared to leaving scheduling up to the OS default. On a single-core
machine this is structurally a no-op (nothing to isolate from).
```
nproc=4

=== Unpinned (OS default scheduling) ===
unpinned                                 sent=  313055 dispatched=  313055 drops=     0 mean=  0.0086ms p50=  0.0081ms p99=  0.0209ms max=   0.5432ms
unpinned                                 sent=  322468 dispatched=  322468 drops=     0 mean=  0.0083ms p50=  0.0079ms p99=  0.0208ms max=   0.5420ms
unpinned                                 sent=  314750 dispatched=  314750 drops=     0 mean=  0.0085ms p50=  0.0080ms p99=  0.0209ms max=   0.5375ms

=== Pinned: publisher->CPU0, subscriber->CPU1 ===
pinned                                   sent=  897122 dispatched=       0 drops=     0 mean=  0.0000ms p50=  0.0000ms p99=  0.0000ms max=   0.0000ms
pinned                                   sent=  430797 dispatched=  430797 drops=     0 mean=  0.0099ms p50=  0.0070ms p99=  0.0389ms max=   0.7994ms
pinned                                   sent= 1302977 dispatched=       0 drops=     0 mean=  0.0000ms p50=  0.0000ms p99=  0.0000ms max=   0.0000ms
```
