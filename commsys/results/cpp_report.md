# commsys C++ benchmark report

Generated: 2026-08-09 15:26:30 UTC

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
1/1 Test #1: commsys_tests ....................***Failed   27.38 sec
Randomness seeded to: 405128701

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
commsys_tests is a Catch2 v3.4.0 host application.
Run with -? for options

-------------------------------------------------------------------------------
ros_compat: SensorDataQoS (depth=1) delivers only the freshest value under load
-------------------------------------------------------------------------------
/home/runner/work/cc-code/cc-code/commsys/cpp/node/tests/test_ros_compat.cpp:67
...............................................................................

/home/runner/work/cc-code/cc-code/commsys/cpp/node/tests/test_ros_compat.cpp:111: FAILED:
  REQUIRE( child.wait() == 0 )
with expansion:
  1 == 0

===============================================================================
test cases:   49 |   48 passed | 1 failed
assertions: 1878 | 1877 passed | 1 failed


    Start 1: commsys_tests
    Test #1: commsys_tests ....................   Passed   27.38 sec

100% tests passed, 0 tests failed out of 1

Total Test time (real) =  54.82 sec
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
[keep_latest] sent=338494 (unpaced firehose)
[keep_latest] dispatched=336937
[keep_latest] mean=0.0070ms p50=0.0069ms p99=0.0087ms max=0.0483ms
-- test_ring_stress --
[fifo ring] sent=533399 (unpaced firehose)
[fifo ring] dispatched=533399 drops=0
[fifo ring] mean=0.0081ms p50=0.0054ms p99=0.0265ms max=1.1509ms
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
| 500Hz shm                    |     1208 |      0 |     0.0155 MB/s |    0.0010ms |    0.0227ms |    0.0298ms |
| 1000Hz shm                   |     2346 |      0 |     0.0300 MB/s |    0.0007ms |    0.0134ms |    0.0230ms |
| 2000Hz shm                   |     4425 |      0 |     0.0566 MB/s |    0.0006ms |    0.0088ms |    0.0599ms |
| 5000Hz shm                   |     9447 |      0 |     0.1209 MB/s |    0.0006ms |    0.0075ms |    0.0179ms |
| 10000Hz shm                  |    15092 |      0 |     0.1932 MB/s |    0.0006ms |    0.0080ms |    0.0271ms |
| 500Hz udp                    |     1209 |      0 |     0.0155 MB/s |    0.0094ms |    0.0179ms |    0.0678ms |
| 1000Hz udp                   |     2345 |      0 |     0.0300 MB/s |    0.0082ms |    0.0149ms |    0.0644ms |
| 2000Hz udp                   |     4415 |      0 |     0.0565 MB/s |    0.0082ms |    0.0155ms |    0.0701ms |
| 5000Hz udp                   |     9340 |      0 |     0.1196 MB/s |    0.0086ms |    0.0161ms |    0.0630ms |
| 10000Hz udp                  |    14901 |      0 |     0.1907 MB/s |    0.0088ms |    0.0153ms |    0.0642ms |

## 2. LaserScan rate sweep (2000-point-equivalent payload, ~8KB)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 10Hz shm                     |       25 |      0 |     0.0806 MB/s |    0.0337ms |    0.0527ms |    0.0527ms |
| 20Hz shm                     |       50 |      0 |     0.1613 MB/s |    0.0233ms |    0.0582ms |    0.0582ms |
| 40Hz shm                     |      100 |      0 |     0.3226 MB/s |    0.0190ms |    0.0566ms |    0.0566ms |
| 60Hz shm                     |      150 |      0 |     0.4838 MB/s |    0.0182ms |    0.0321ms |    0.0496ms |
| 10Hz udp                     |       25 |      0 |     0.0806 MB/s |    0.0771ms |    0.1250ms |    0.1250ms |
| 20Hz udp                     |       50 |      0 |     0.1613 MB/s |    0.0638ms |    0.1203ms |    0.1203ms |
| 40Hz udp                     |      100 |      0 |     0.3226 MB/s |    0.0572ms |    0.1176ms |    0.1176ms |
| 60Hz udp                     |      150 |      0 |     0.4838 MB/s |    0.0549ms |    0.0804ms |    0.1119ms |

## 3. Unpaced firehose (worst case, no publisher pacing at all)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 64KB FIFO ring, shm          |   477807 |      0 | 15656.7798 MB/s |    0.0074ms |    0.0264ms |    0.6600ms |


## CPU core affinity comparison

Tests whether pinning the publisher and subscriber to dedicated CPU
cores (sched_setaffinity) reduces scheduling-contention tail latency,
compared to leaving scheduling up to the OS default. On a single-core
machine this is structurally a no-op (nothing to isolate from).
```
nproc=4

=== Unpinned (OS default scheduling) ===
unpinned                                 sent=  430646 dispatched=  430646 drops=     0 mean=  0.0077ms p50=  0.0063ms p99=  0.0269ms max=   0.6416ms
unpinned                                 sent=  545759 dispatched=  545759 drops=     0 mean=  0.0066ms p50=  0.0053ms p99=  0.0259ms max=   0.6515ms
unpinned                                 sent=  547643 dispatched=  547643 drops=     0 mean=  0.0075ms p50=  0.0053ms p99=  0.0265ms max=   0.7083ms

=== Pinned: publisher->CPU0, subscriber->CPU1 ===
pinned                                   sent=  356317 dispatched=  356317 drops=     0 mean=  0.0130ms p50=  0.0078ms p99=  0.0522ms max=   0.9294ms
pinned                                   sent=  333292 dispatched=  333292 drops=     0 mean=  0.0124ms p50=  0.0080ms p99=  0.0516ms max=   0.9440ms
pinned                                   sent=  268734 dispatched=  268734 drops=     0 mean=  0.0123ms p50=  0.0091ms p99=  0.0537ms max=   0.8975ms
```
