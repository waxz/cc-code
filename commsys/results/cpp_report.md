# commsys C++ benchmark report

Generated: 2026-08-02 02:30:09 UTC

## Hardware
```
vCPUs: 1
               total        used        free      shared  buff/cache   available
Mem:           3.9Gi       347Mi       3.4Gi       4.2Mi       425Mi       3.6Gi
Swap:             0B          0B          0B
Linux vm 6.18.5 #1 SMP PREEMPT_DYNAMIC @0 x86_64 x86_64 x86_64 GNU/Linux
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
[keep_latest] sent=2824 (unpaced firehose)
[keep_latest] dispatched=693
[keep_latest] mean=0.0993ms p50=0.0062ms p99=0.0115ms max=64.2361ms
-- test_ring_stress --
[fifo ring] sent=62822 (unpaced firehose)
[fifo ring] dispatched=62817 drops=0
[fifo ring] mean=4.5422ms p50=3.6525ms p99=6.5796ms max=306.5477ms
```

## Full benchmark sweep

# commsys C++ benchmark report

Same scenario matrix as benchmark_report.py, same machine, same 2.5s steady-state duration after 0.8s discovery settle.

## 1. IMU rate sweep (single publisher -> single subscriber, 32B payload)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 500Hz shm                    |     1207 |      0 |     0.0154 MB/s |    0.0056ms |    0.0291ms |    0.1184ms |
| 1000Hz shm                   |     2328 |      0 |     0.0298 MB/s |    0.0073ms |    0.0249ms |    1.1578ms |
| 2000Hz shm                   |     4334 |      0 |     0.0555 MB/s |    0.0083ms |    0.0251ms |    0.0595ms |
| 5000Hz shm                   |     9170 |      0 |     0.1174 MB/s |    0.0090ms |    0.0242ms |    1.2798ms |
| 10000Hz shm                  |    14462 |      0 |     0.1851 MB/s |    0.0091ms |    0.0220ms |    1.3817ms |
| 500Hz udp                    |     1202 |      0 |     0.0154 MB/s |    0.0128ms |    0.0463ms |    1.1678ms |
| 1000Hz udp                   |     2328 |      0 |     0.0298 MB/s |    0.0117ms |    0.0311ms |    0.0832ms |
| 2000Hz udp                   |     4348 |      0 |     0.0557 MB/s |    0.0126ms |    0.0358ms |    1.2085ms |
| 5000Hz udp                   |     9210 |      0 |     0.1179 MB/s |    0.0123ms |    0.0259ms |    1.3277ms |
| 10000Hz udp                  |    14576 |      0 |     0.1866 MB/s |    0.0123ms |    0.0248ms |    1.2244ms |

## 2. LaserScan rate sweep (2000-point-equivalent payload, ~8KB)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 10Hz shm                     |       25 |      0 |     0.0806 MB/s |    0.0426ms |    0.0771ms |    0.0771ms |
| 20Hz shm                     |       50 |      0 |     0.1613 MB/s |    0.0319ms |    0.0492ms |    0.0492ms |
| 40Hz shm                     |      100 |      0 |     0.3226 MB/s |    0.0241ms |    0.0595ms |    0.0595ms |
| 60Hz shm                     |      150 |      0 |     0.4838 MB/s |    0.0218ms |    0.0431ms |    0.0441ms |
| 10Hz udp                     |       25 |      0 |     0.0806 MB/s |    0.0665ms |    0.0949ms |    0.0949ms |
| 20Hz udp                     |       50 |      0 |     0.1613 MB/s |    0.0477ms |    0.0872ms |    0.0872ms |
| 40Hz udp                     |      100 |      0 |     0.3226 MB/s |    0.0347ms |    0.0954ms |    0.0954ms |
| 60Hz udp                     |      150 |      0 |     0.4838 MB/s |    0.0314ms |    0.0823ms |    0.0942ms |

## 3. Unpaced firehose (worst case, no publisher pacing at all)

| scenario                     |    msgs |  drops |    bandwidth |      mean |       p99 |       max |
|------------------------------|---------|--------|--------------|-----------|-----------|-----------|
| 64KB FIFO ring, shm          |    65350 |      0 |  2141.3888 MB/s |    4.4596ms |    7.1431ms |  307.6828ms |

