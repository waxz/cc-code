# commsys C++ benchmark report

Generated: 2026-08-07 21:08:25 UTC

## Hardware
```
vCPUs: 4
               total        used        free      shared  buff/cache   available
Mem:            15Gi       964Mi        11Gi        45Mi       3.2Gi        14Gi
Swap:          3.0Gi          0B       3.0Gi
Linux runnervmvrwv9 6.17.0-1020-azure #20~24.04.1-Ubuntu SMP Fri Jun 19 20:09:14 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
```

## Unit tests (ctest / Catch2)
```
Test project /home/runner/work/cc-code/cc-code/commsys/cpp/build
    Start 1: commsys_tests
1/1 Test #1: commsys_tests ....................   Passed   27.39 sec

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
[keep_latest] sent=162748 (unpaced firehose)
[keep_latest] dispatched=154584
[keep_latest] mean=0.0137ms p50=0.0136ms p99=0.0188ms max=0.0944ms
-- test_ring_stress --
[fifo ring] sent=425437 (unpaced firehose)
[fifo ring] dispatched=425437 drops=0
[fifo ring] mean=0.0079ms p50=0.0069ms p99=0.0268ms max=0.6064ms
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
| 500Hz shm                    |     1200 |      0 |     0.0154 MB/s |    0.0015ms |    0.0304ms |    0.0527ms |
| 1000Hz shm                   |     2353 |      0 |     0.0301 MB/s |    0.0011ms |    0.0216ms |    0.0313ms |
| 2000Hz shm                   |     4447 |      0 |     0.0569 MB/s |    0.0009ms |    0.0165ms |    0.0369ms |
| 5000Hz shm                   |     9484 |      0 |     0.1214 MB/s |    0.0009ms |    0.0124ms |    0.1085ms |
| 10000Hz shm                  |    15453 |      0 |     0.1978 MB/s |    0.0008ms |    0.0101ms |    0.0375ms |
| 500Hz udp                    |     1200 |      0 |     0.0154 MB/s |    0.0182ms |    0.0401ms |    0.0816ms |
| 1000Hz udp                   |     2354 |      0 |     0.0301 MB/s |    0.0085ms |    0.0139ms |    0.0862ms |
| 2000Hz udp                   |     4453 |      0 |     0.0570 MB/s |    0.0079ms |    0.0149ms |    0.0922ms |
| 5000Hz udp                   |     9566 |      0 |     0.1224 MB/s |    0.0075ms |    0.0120ms |    0.0830ms |
| 10000Hz udp                  |    15442 |      0 |     0.1977 MB/s |    0.0081ms |    0.0182ms |    0.0859ms |

## 2. LaserScan rate sweep (2000-point-equivalent payload, ~8KB)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 10Hz shm                     |       25 |      0 |     0.0806 MB/s |    0.0374ms |    0.0567ms |    0.0567ms |
| 20Hz shm                     |       50 |      0 |     0.1613 MB/s |    0.0319ms |    0.0788ms |    0.0788ms |
| 40Hz shm                     |      100 |      0 |     0.3226 MB/s |    0.0253ms |    0.0613ms |    0.0613ms |
| 60Hz shm                     |      150 |      0 |     0.4838 MB/s |    0.0228ms |    0.0663ms |    0.0898ms |
| 10Hz udp                     |       25 |      0 |     0.0806 MB/s |    0.0938ms |    0.1539ms |    0.1539ms |
| 20Hz udp                     |       50 |      0 |     0.1613 MB/s |    0.0770ms |    0.1343ms |    0.1343ms |
| 40Hz udp                     |      100 |      0 |     0.3226 MB/s |    0.0649ms |    0.1393ms |    0.1393ms |
| 60Hz udp                     |      150 |      0 |     0.4838 MB/s |    0.0608ms |    0.1023ms |    0.1435ms |

## 3. Unpaced firehose (worst case, no publisher pacing at all)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 64KB FIFO ring, shm          |   424791 |      0 | 13919.5515 MB/s |    0.0079ms |    0.0285ms |    0.6167ms |


## CPU core affinity comparison

Tests whether pinning the publisher and subscriber to dedicated CPU
cores (sched_setaffinity) reduces scheduling-contention tail latency,
compared to leaving scheduling up to the OS default. On a single-core
machine this is structurally a no-op (nothing to isolate from).
```
nproc=4

=== Unpinned (OS default scheduling) ===
unpinned                                 sent=  426359 dispatched=  426359 drops=     0 mean=  0.0079ms p50=  0.0069ms p99=  0.0284ms max=   0.6039ms
unpinned                                 sent= 1164370 dispatched=       0 drops=     0 mean=  0.0000ms p50=  0.0000ms p99=  0.0000ms max=   0.0000ms
unpinned                                 sent=  487720 dispatched=  487720 drops=     0 mean=  0.0074ms p50=  0.0063ms p99=  0.0281ms max=   0.6008ms

=== Pinned: publisher->CPU0, subscriber->CPU1 ===
pinned                                   sent=  338266 dispatched=  338266 drops=     0 mean=  0.0126ms p50=  0.0089ms p99=  0.0499ms max=   0.9836ms
pinned                                   sent=  347827 dispatched=  347827 drops=     0 mean=  0.0130ms p50=  0.0088ms p99=  0.0504ms max=   1.0074ms
pinned                                   sent=  295734 dispatched=  295734 drops=     0 mean=  0.0119ms p50=  0.0093ms p99=  0.0494ms max=   0.9655ms
```
