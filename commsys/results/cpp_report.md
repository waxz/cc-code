# commsys C++ benchmark report

Generated: 2026-08-02 05:37:24 UTC

## Hardware
```
vCPUs: 4
               total        used        free      shared  buff/cache   available
Mem:            15Gi       1.0Gi        12Gi        46Mi       2.9Gi        14Gi
Swap:          3.0Gi          0B       3.0Gi
Linux runnervmvrwv9 6.17.0-1020-azure #20~24.04.1-Ubuntu SMP Fri Jun 19 20:09:14 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
```

## Unit tests (ctest / Catch2)
```
Test project /home/runner/work/cc-code/cc-code/commsys/cpp/build
    Start 1: commsys_tests
1/1 Test #1: commsys_tests ....................***Failed   11.58 sec
Randomness seeded to: 2832528163

~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
commsys_tests is a Catch2 v3.4.0 host application.
Run with -? for options

-------------------------------------------------------------------------------
Node: keep_latest subscriber sees the freshest value, not a backlog
-------------------------------------------------------------------------------
/home/runner/work/cc-code/cc-code/commsys/cpp/node/tests/test_node.cpp:109
...............................................................................

/home/runner/work/cc-code/cc-code/commsys/cpp/node/tests/test_node.cpp:144: FAILED:
  REQUIRE( rc == 0 )
with expansion:
  2 == 0

===============================================================================
test cases:   44 |   43 passed | 1 failed
assertions: 1870 | 1869 passed | 1 failed



0% tests passed, 1 tests failed out of 1

Total Test time (real) =  11.66 sec

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
[keep_latest] sent=325157 (unpaced firehose)
[keep_latest] dispatched=322903
[keep_latest] mean=0.0073ms p50=0.0071ms p99=0.0098ms max=0.0660ms
-- test_ring_stress --
[fifo ring] sent=561085 (unpaced firehose)
[fifo ring] dispatched=561085 drops=0
[fifo ring] mean=0.0072ms p50=0.0052ms p99=0.0261ms max=0.6956ms
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
| 500Hz shm                    |     1209 |      0 |     0.0155 MB/s |    0.0008ms |    0.0170ms |    0.0255ms |
| 1000Hz shm                   |     2344 |      0 |     0.0300 MB/s |    0.0007ms |    0.0105ms |    0.0311ms |
| 2000Hz shm                   |     4429 |      0 |     0.0567 MB/s |    0.0006ms |    0.0082ms |    0.0236ms |
| 5000Hz shm                   |     9417 |      0 |     0.1205 MB/s |    0.0006ms |    0.0080ms |    0.0193ms |
| 10000Hz shm                  |    15196 |      0 |     0.1945 MB/s |    0.0006ms |    0.0070ms |    0.0524ms |
| 500Hz udp                    |     1209 |      0 |     0.0155 MB/s |    0.0100ms |    0.0169ms |    0.0602ms |
| 1000Hz udp                   |     2345 |      0 |     0.0300 MB/s |    0.0084ms |    0.0159ms |    0.0527ms |
| 2000Hz udp                   |     4422 |      0 |     0.0566 MB/s |    0.0078ms |    0.0127ms |    0.0553ms |
| 5000Hz udp                   |     9392 |      0 |     0.1202 MB/s |    0.0082ms |    0.0146ms |    0.0540ms |
| 10000Hz udp                  |    14896 |      0 |     0.1907 MB/s |    0.0091ms |    0.0157ms |    0.0546ms |

## 2. LaserScan rate sweep (2000-point-equivalent payload, ~8KB)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 10Hz shm                     |       25 |      0 |     0.0806 MB/s |    0.0280ms |    0.0396ms |    0.0396ms |
| 20Hz shm                     |       50 |      0 |     0.1613 MB/s |    0.0216ms |    0.0540ms |    0.0540ms |
| 40Hz shm                     |      100 |      0 |     0.3226 MB/s |    0.0178ms |    0.0483ms |    0.0483ms |
| 60Hz shm                     |      150 |      0 |     0.4838 MB/s |    0.0173ms |    0.0405ms |    0.0760ms |
| 10Hz udp                     |       25 |      0 |     0.0806 MB/s |    0.0684ms |    0.1117ms |    0.1117ms |
| 20Hz udp                     |       50 |      0 |     0.1613 MB/s |    0.0696ms |    0.1109ms |    0.1109ms |
| 40Hz udp                     |      100 |      0 |     0.3226 MB/s |    0.0583ms |    0.1159ms |    0.1159ms |
| 60Hz udp                     |      150 |      0 |     0.4838 MB/s |    0.0568ms |    0.0809ms |    0.1065ms |

## 3. Unpaced firehose (worst case, no publisher pacing at all)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 64KB FIFO ring, shm          |   559767 |      0 | 18342.4451 MB/s |    0.0081ms |    0.0286ms |    1.1275ms |


## CPU core affinity comparison

Tests whether pinning the publisher and subscriber to dedicated CPU
cores (sched_setaffinity) reduces scheduling-contention tail latency,
compared to leaving scheduling up to the OS default. On a single-core
machine this is structurally a no-op (nothing to isolate from).
```
nproc=4

=== Unpinned (OS default scheduling) ===
unpinned                                 sent=  528356 dispatched=  528356 drops=     0 mean=  0.0083ms p50=  0.0054ms p99=  0.0294ms max=   1.1260ms
unpinned                                 sent=  559156 dispatched=  559156 drops=     0 mean=  0.0073ms p50=  0.0052ms p99=  0.0261ms max=   1.1013ms
unpinned                                 sent=  452157 dispatched=  452157 drops=     0 mean=  0.0079ms p50=  0.0061ms p99=  0.0269ms max=   0.9380ms

=== Pinned: publisher->CPU0, subscriber->CPU1 ===
pinned                                   sent=  346283 dispatched=  346283 drops=     0 mean=  0.0134ms p50=  0.0080ms p99=  0.0521ms max=   1.2141ms
pinned                                   sent=  380100 dispatched=  380100 drops=     0 mean=  0.0149ms p50=  0.0077ms p99=  0.0555ms max=   1.2512ms
pinned                                   sent=  349924 dispatched=  349924 drops=     0 mean=  0.0141ms p50=  0.0081ms p99=  0.0520ms max=   1.2606ms
```
