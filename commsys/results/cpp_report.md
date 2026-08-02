# commsys C++ benchmark report

Generated: 2026-08-02 02:39:49 UTC

## Hardware
```
vCPUs: 4
               total        used        free      shared  buff/cache   available
Mem:            15Gi       1.0Gi        11Gi        47Mi       3.1Gi        14Gi
Swap:          3.0Gi          0B       3.0Gi
Linux runnervmvrwv9 6.17.0-1020-azure #20~24.04.1-Ubuntu SMP Fri Jun 19 20:09:14 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux
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
[keep_latest] sent=390820 (unpaced firehose)
[keep_latest] dispatched=388673
[keep_latest] mean=0.0062ms p50=0.0061ms p99=0.0091ms max=0.0685ms
-- test_ring_stress --
[fifo ring] sent=236017 (unpaced firehose)
[fifo ring] dispatched=236012 drops=0
[fifo ring] mean=0.3341ms p50=0.0091ms p99=0.0290ms max=300.0882ms
```

## Full benchmark sweep

# commsys C++ benchmark report

Same scenario matrix as benchmark_report.py, same machine, same 2.5s steady-state duration after 0.8s discovery settle.

## 1. IMU rate sweep (single publisher -> single subscriber, 32B payload)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 500Hz shm                    |     1208 |      0 |     0.0155 MB/s |    0.0009ms |    0.0192ms |    0.0322ms |
| 1000Hz shm                   |     2343 |      0 |     0.0300 MB/s |    0.0008ms |    0.0134ms |    0.0569ms |
| 2000Hz shm                   |     4415 |      0 |     0.0565 MB/s |    0.0007ms |    0.0099ms |    0.0814ms |
| 5000Hz shm                   |     9401 |      0 |     0.1203 MB/s |    0.0006ms |    0.0084ms |    0.0188ms |
| 10000Hz shm                  |    15141 |      0 |     0.1938 MB/s |    0.0006ms |    0.0075ms |    0.0202ms |
| 500Hz udp                    |     1206 |      0 |     0.0154 MB/s |    0.0113ms |    0.0199ms |    0.0744ms |
| 1000Hz udp                   |     2342 |      0 |     0.0300 MB/s |    0.0089ms |    0.0159ms |    0.0666ms |
| 2000Hz udp                   |     4393 |      0 |     0.0562 MB/s |    0.0099ms |    0.0151ms |    0.0685ms |
| 5000Hz udp                   |     9389 |      0 |     0.1202 MB/s |    0.0081ms |    0.0126ms |    0.0603ms |
| 10000Hz udp                  |    14992 |      0 |     0.1919 MB/s |    0.0084ms |    0.0156ms |    0.0576ms |

## 2. LaserScan rate sweep (2000-point-equivalent payload, ~8KB)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 10Hz shm                     |       25 |      0 |     0.0806 MB/s |    0.0270ms |    0.0542ms |    0.0542ms |
| 20Hz shm                     |       50 |      0 |     0.1613 MB/s |    0.0222ms |    0.0534ms |    0.0534ms |
| 40Hz shm                     |      100 |      0 |     0.3226 MB/s |    0.0193ms |    0.0500ms |    0.0500ms |
| 60Hz shm                     |      150 |      0 |     0.4838 MB/s |    0.0157ms |    0.0286ms |    0.0617ms |
| 10Hz udp                     |       25 |      0 |     0.0806 MB/s |    0.0735ms |    0.1149ms |    0.1149ms |
| 20Hz udp                     |       50 |      0 |     0.1613 MB/s |    0.0609ms |    0.1144ms |    0.1144ms |
| 40Hz udp                     |      100 |      0 |     0.3226 MB/s |    0.0565ms |    0.1143ms |    0.1143ms |
| 60Hz udp                     |      150 |      0 |     0.4838 MB/s |    0.0557ms |    0.0818ms |    0.1190ms |

## 3. Unpaced firehose (worst case, no publisher pacing at all)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 64KB FIFO ring, shm          |   253000 |      0 |  8290.3040 MB/s |    0.3121ms |    0.0287ms |  300.3899ms |

