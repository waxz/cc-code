# commsys C++ benchmark report

Generated: 2026-08-02 05:29:43 UTC

## Hardware
```
vCPUs: 1
               total        used        free      shared  buff/cache   available
Mem:           3.9Gi       363Mi       3.3Gi       4.2Mi       483Mi       3.5Gi
Swap:             0B          0B          0B
Linux vm 6.18.5 #1 SMP PREEMPT_DYNAMIC @0 x86_64 x86_64 x86_64 GNU/Linux
```

## Unit tests (ctest / Catch2)
```
Test project /home/claude/commsys/commsys/cpp/build
    Start 1: commsys_tests
1/1 Test #1: commsys_tests ....................   Passed   11.61 sec

100% tests passed, 0 tests failed out of 1

Total Test time (real) =  11.61 sec
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
[keep_latest] sent=2822 (unpaced firehose)
[keep_latest] dispatched=767
[keep_latest] mean=0.0069ms p50=0.0065ms p99=0.0113ms max=0.0670ms
-- test_ring_stress --
[fifo ring] sent=125167 (unpaced firehose)
[fifo ring] dispatched=125167 drops=0
[fifo ring] mean=1.4986ms p50=1.4218ms p99=2.8178ms max=8.1307ms
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
| 500Hz shm                    |     1198 |      0 |     0.0153 MB/s |    0.0081ms |    0.0364ms |    0.0885ms |
| 1000Hz shm                   |     2294 |      0 |     0.0294 MB/s |    0.0109ms |    0.0402ms |    0.0719ms |
| 2000Hz shm                   |     4241 |      0 |     0.0543 MB/s |    0.0125ms |    0.0397ms |    0.0690ms |
| 5000Hz shm                   |     8757 |      0 |     0.1121 MB/s |    0.0137ms |    0.0386ms |    1.6309ms |
| 10000Hz shm                  |    13340 |      0 |     0.1708 MB/s |    0.0150ms |    0.0406ms |    1.8135ms |
| 500Hz udp                    |     1198 |      0 |     0.0153 MB/s |    0.0215ms |    0.0510ms |    1.6008ms |
| 1000Hz udp                   |     2288 |      0 |     0.0293 MB/s |    0.0236ms |    0.0547ms |    1.6245ms |
| 2000Hz udp                   |     4245 |      0 |     0.0543 MB/s |    0.0216ms |    0.0458ms |    1.8236ms |
| 5000Hz udp                   |     8744 |      0 |     0.1119 MB/s |    0.0219ms |    0.0422ms |    1.9196ms |
| 10000Hz udp                  |    13502 |      0 |     0.1728 MB/s |    0.0213ms |    0.0421ms |    1.8780ms |

## 2. LaserScan rate sweep (2000-point-equivalent payload, ~8KB)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 10Hz shm                     |       25 |      0 |     0.0806 MB/s |    0.0500ms |    0.0848ms |    0.0848ms |
| 20Hz shm                     |       50 |      0 |     0.1613 MB/s |    0.0469ms |    0.0732ms |    0.0732ms |
| 40Hz shm                     |      100 |      0 |     0.3226 MB/s |    0.0680ms |    2.6169ms |    2.6169ms |
| 60Hz shm                     |      149 |      0 |     0.4806 MB/s |    0.0380ms |    0.1131ms |    0.1208ms |
| 10Hz udp                     |       25 |      0 |     0.0806 MB/s |    0.0935ms |    0.1226ms |    0.1226ms |
| 20Hz udp                     |       50 |      0 |     0.1613 MB/s |    0.0896ms |    0.1377ms |    0.1377ms |
| 40Hz udp                     |      100 |      0 |     0.3226 MB/s |    0.0912ms |    0.1852ms |    0.1852ms |
| 60Hz udp                     |      149 |      0 |     0.4806 MB/s |    0.0769ms |    0.1280ms |    0.1337ms |

## 3. Unpaced firehose (worst case, no publisher pacing at all)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 64KB FIFO ring, shm          |   125234 |      0 |  4103.6677 MB/s |    1.4342ms |    2.8580ms |    8.9611ms |


## CPU core affinity comparison

Tests whether pinning the publisher and subscriber to dedicated CPU
cores (sched_setaffinity) reduces scheduling-contention tail latency,
compared to leaving scheduling up to the OS default. On a single-core
machine this is structurally a no-op (nothing to isolate from).
```
nproc=1

Only 1 CPU available -- core isolation is structurally meaningless here
(nothing to isolate the publisher and subscriber FROM; they must share
the single core regardless of any affinity setting). Running the
unpinned case only, for the record:

unpinned (only option on 1 core)         sent=  108415 dispatched=  108415 drops=     0 mean=  1.3903ms p50=  1.2639ms p99=  4.0169ms max=  36.1205ms
```
