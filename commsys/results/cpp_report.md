# commsys C++ benchmark report

Generated: 2026-08-08 15:35:16 UTC

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
Randomness seeded to: 388051552

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
commsys_tests is a Catch2 v3.4.0 host application.
Run with -? for options

-------------------------------------------------------------------------------
Node: keep_latest subscriber sees the freshest value, not a backlog
-------------------------------------------------------------------------------
/home/runner/work/cc-code/cc-code/commsys/cpp/node/tests/test_node.cpp:109
...............................................................................

/home/runner/work/cc-code/cc-code/commsys/cpp/node/tests/test_node.cpp:160: FAILED:
  REQUIRE( rc == 0 )
with expansion:
  1 == 0

===============================================================================
test cases:   49 |   48 passed | 1 failed
assertions: 1878 | 1877 passed | 1 failed



0% tests passed, 1 tests failed out of 1

Total Test time (real) =  27.45 sec

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
[keep_latest] sent=350346 (unpaced firehose)
[keep_latest] dispatched=348653
[keep_latest] mean=0.0069ms p50=0.0067ms p99=0.0100ms max=0.0361ms
-- test_ring_stress --
[fifo ring] sent=547375 (unpaced firehose)
[fifo ring] dispatched=547375 drops=0
[fifo ring] mean=0.0080ms p50=0.0053ms p99=0.0262ms max=1.1655ms
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
| 500Hz shm                    |     1209 |      0 |     0.0155 MB/s |    0.0009ms |    0.0130ms |    0.0459ms |
| 1000Hz shm                   |     2341 |      0 |     0.0300 MB/s |    0.0007ms |    0.0094ms |    0.0135ms |
| 2000Hz shm                   |     4401 |      0 |     0.0563 MB/s |    0.0007ms |    0.0095ms |    0.0293ms |
| 5000Hz shm                   |     9437 |      0 |     0.1208 MB/s |    0.0006ms |    0.0076ms |    0.0165ms |
| 10000Hz shm                  |    15179 |      0 |     0.1943 MB/s |    0.0006ms |    0.0070ms |    0.0300ms |
| 500Hz udp                    |     1209 |      0 |     0.0155 MB/s |    0.0092ms |    0.0162ms |    0.0518ms |
| 1000Hz udp                   |     2343 |      0 |     0.0300 MB/s |    0.0089ms |    0.0157ms |    0.0730ms |
| 2000Hz udp                   |     4415 |      0 |     0.0565 MB/s |    0.0083ms |    0.0143ms |    0.0528ms |
| 5000Hz udp                   |     9351 |      0 |     0.1197 MB/s |    0.0088ms |    0.0159ms |    0.0568ms |
| 10000Hz udp                  |    15078 |      0 |     0.1930 MB/s |    0.0080ms |    0.0130ms |    0.0596ms |

## 2. LaserScan rate sweep (2000-point-equivalent payload, ~8KB)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 10Hz shm                     |       25 |      0 |     0.0806 MB/s |    0.0252ms |    0.0347ms |    0.0347ms |
| 20Hz shm                     |       50 |      0 |     0.1613 MB/s |    0.0230ms |    0.0491ms |    0.0491ms |
| 40Hz shm                     |      100 |      0 |     0.3226 MB/s |    0.0215ms |    0.0502ms |    0.0502ms |
| 60Hz shm                     |      150 |      0 |     0.4838 MB/s |    0.0175ms |    0.0358ms |    0.0582ms |
| 10Hz udp                     |       25 |      0 |     0.0806 MB/s |    0.0855ms |    0.1174ms |    0.1174ms |
| 20Hz udp                     |       50 |      0 |     0.1613 MB/s |    0.0757ms |    0.1159ms |    0.1159ms |
| 40Hz udp                     |      100 |      0 |     0.3226 MB/s |    0.0622ms |    0.1126ms |    0.1126ms |
| 60Hz udp                     |      150 |      0 |     0.4838 MB/s |    0.0569ms |    0.0695ms |    0.1118ms |

## 3. Unpaced firehose (worst case, no publisher pacing at all)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 64KB FIFO ring, shm          |   542162 |      0 | 17765.5644 MB/s |    0.0075ms |    0.0263ms |    0.7355ms |


## CPU core affinity comparison

Tests whether pinning the publisher and subscriber to dedicated CPU
cores (sched_setaffinity) reduces scheduling-contention tail latency,
compared to leaving scheduling up to the OS default. On a single-core
machine this is structurally a no-op (nothing to isolate from).
```
nproc=4

=== Unpinned (OS default scheduling) ===
unpinned                                 sent=  272389 dispatched=  272389 drops=     0 mean=  0.0102ms p50=  0.0088ms p99=  0.0293ms max=   0.8930ms
unpinned                                 sent=  397619 dispatched=  397619 drops=     0 mean=  0.0081ms p50=  0.0064ms p99=  0.0264ms max=   0.9682ms
unpinned                                 sent=  456458 dispatched=  456458 drops=     0 mean=  0.0081ms p50=  0.0057ms p99=  0.0268ms max=   0.8935ms

=== Pinned: publisher->CPU0, subscriber->CPU1 ===
pinned                                   sent=  320115 dispatched=  320115 drops=     0 mean=  0.0133ms p50=  0.0085ms p99=  0.0503ms max=   1.2256ms
pinned                                   sent=  243719 dispatched=  243719 drops=     0 mean=  0.0127ms p50=  0.0101ms p99=  0.0528ms max=   0.8666ms
pinned                                   sent=  346962 dispatched=  346962 drops=     0 mean=  0.0142ms p50=  0.0082ms p99=  0.0519ms max=   1.2955ms
```
