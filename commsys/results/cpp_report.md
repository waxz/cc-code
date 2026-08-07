# commsys C++ benchmark report

Generated: 2026-08-07 20:59:19 UTC

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
1/1 Test #1: commsys_tests ....................***Failed   27.39 sec
Randomness seeded to: 2868154798

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
commsys_tests is a Catch2 v3.4.0 host application.
Run with -? for options

-------------------------------------------------------------------------------
Node: keep_latest subscriber sees the freshest value, not a backlog
-------------------------------------------------------------------------------
/home/runner/work/cc-code/cc-code/commsys/cpp/node/tests/test_node.cpp:109
...............................................................................

/home/runner/work/cc-code/cc-code/commsys/cpp/node/tests/test_node.cpp:145: FAILED:
  REQUIRE( rc == 0 )
with expansion:
  2 == 0

-------------------------------------------------------------------------------
ros_compat: SensorDataQoS (depth=1) delivers only the freshest value under load
-------------------------------------------------------------------------------
/home/runner/work/cc-code/cc-code/commsys/cpp/node/tests/test_ros_compat.cpp:67
...............................................................................

/home/runner/work/cc-code/cc-code/commsys/cpp/node/tests/test_ros_compat.cpp:106: FAILED:
  REQUIRE( child.wait() == 0 )
with expansion:
  1 == 0

===============================================================================
test cases:   49 |   47 passed | 2 failed
assertions: 1878 | 1876 passed | 2 failed



0% tests passed, 1 tests failed out of 1

Total Test time (real) =  27.46 sec

The following tests FAILED:
	  1 - commsys_tests (Failed)
Errors while running CTest
(unit tests unavailable or failed -- see above; Catch2 may not be installed)
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
[keep_latest] sent=155702 (unpaced firehose)
[keep_latest] dispatched=153554
[keep_latest] mean=0.0143ms p50=0.0140ms p99=0.0221ms max=0.0598ms
-- test_ring_stress --
[fifo ring] sent=423703 (unpaced firehose)
[fifo ring] dispatched=423703 drops=0
[fifo ring] mean=0.0082ms p50=0.0069ms p99=0.0285ms max=0.9531ms
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
| 500Hz shm                    |     1200 |      0 |     0.0154 MB/s |    0.0014ms |    0.0272ms |    0.0388ms |
| 1000Hz shm                   |     2350 |      0 |     0.0301 MB/s |    0.0010ms |    0.0196ms |    0.0390ms |
| 2000Hz shm                   |     4452 |      0 |     0.0570 MB/s |    0.0010ms |    0.0138ms |    0.0303ms |
| 5000Hz shm                   |     9575 |      0 |     0.1226 MB/s |    0.0009ms |    0.0095ms |    0.0224ms |
| 10000Hz shm                  |    15523 |      0 |     0.1987 MB/s |    0.0008ms |    0.0081ms |    0.0573ms |
| 500Hz udp                    |     1201 |      0 |     0.0154 MB/s |    0.0168ms |    0.0339ms |    0.0753ms |
| 1000Hz udp                   |     2351 |      0 |     0.0301 MB/s |    0.0095ms |    0.0199ms |    0.0686ms |
| 2000Hz udp                   |     4449 |      0 |     0.0569 MB/s |    0.0082ms |    0.0190ms |    0.0669ms |
| 5000Hz udp                   |     9585 |      0 |     0.1227 MB/s |    0.0073ms |    0.0100ms |    0.0678ms |
| 10000Hz udp                  |    15313 |      0 |     0.1960 MB/s |    0.0085ms |    0.0196ms |    0.1789ms |

## 2. LaserScan rate sweep (2000-point-equivalent payload, ~8KB)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 10Hz shm                     |       25 |      0 |     0.0806 MB/s |    0.0378ms |    0.0638ms |    0.0638ms |
| 20Hz shm                     |       50 |      0 |     0.1613 MB/s |    0.0306ms |    0.0623ms |    0.0623ms |
| 40Hz shm                     |      100 |      0 |     0.3226 MB/s |    0.0255ms |    0.0701ms |    0.0701ms |
| 60Hz shm                     |      150 |      0 |     0.4838 MB/s |    0.0226ms |    0.0618ms |    0.0688ms |
| 10Hz udp                     |       25 |      0 |     0.0806 MB/s |    0.0916ms |    0.1310ms |    0.1310ms |
| 20Hz udp                     |       50 |      0 |     0.1613 MB/s |    0.0849ms |    0.1314ms |    0.1314ms |
| 40Hz udp                     |      100 |      0 |     0.3226 MB/s |    0.0689ms |    0.1267ms |    0.1267ms |
| 60Hz udp                     |      150 |      0 |     0.4838 MB/s |    0.0668ms |    0.1236ms |    0.1258ms |

## 3. Unpaced firehose (worst case, no publisher pacing at all)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 64KB FIFO ring, shm          |   434591 |      0 | 14240.6779 MB/s |    0.0078ms |    0.0283ms |    0.5640ms |


## CPU core affinity comparison

Tests whether pinning the publisher and subscriber to dedicated CPU
cores (sched_setaffinity) reduces scheduling-contention tail latency,
compared to leaving scheduling up to the OS default. On a single-core
machine this is structurally a no-op (nothing to isolate from).
```
nproc=4

=== Unpinned (OS default scheduling) ===
unpinned                                 sent=  392195 dispatched=  392195 drops=     0 mean=  0.0085ms p50=  0.0072ms p99=  0.0287ms max=   0.8207ms
unpinned                                 sent=  440633 dispatched=  440633 drops=     0 mean=  0.0080ms p50=  0.0067ms p99=  0.0282ms max=   0.7801ms
unpinned                                 sent=  434360 dispatched=  434360 drops=     0 mean=  0.0080ms p50=  0.0068ms p99=  0.0284ms max=   0.7783ms

=== Pinned: publisher->CPU0, subscriber->CPU1 ===
pinned                                   sent=  302009 dispatched=  302009 drops=     0 mean=  0.0141ms p50=  0.0097ms p99=  0.0524ms max=   1.2333ms
pinned                                   sent= 1011050 dispatched=       0 drops=     0 mean=  0.0000ms p50=  0.0000ms p99=  0.0000ms max=   0.0000ms
pinned                                   sent=  297069 dispatched=  297069 drops=     0 mean=  0.0137ms p50=  0.0097ms p99=  0.0514ms max=   1.2305ms
```
