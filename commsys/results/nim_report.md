# commsys Nim benchmark report

Generated: 2026-08-09 07:26:43 UTC

## Hardware
```
vCPUs: 4
               total        used        free      shared  buff/cache   available
Mem:            15Gi       1.0Gi        10Gi        48Mi       4.8Gi        14Gi
Swap:          3.0Gi          0B       3.0Gi
Nim Compiler Version 1.6.14 [Linux: amd64]
```

## bench_struct.nim (raw struct pack/unpack)
```
=== Nim raw struct IMU batch (n=20 samples/msg) ===
  pack (copyMem)                   mean=    0.04us  p50=    0.04us  p99=    0.04us  size=    640B
  unpack+sum (in place, no copy)   mean=    0.03us  p50=    0.03us  p99=    0.03us  size=    640B

=== Nim raw struct IMU (n=1 sample/msg) ===
  pack (copyMem)                   mean=    0.02us  p50=    0.02us  p99=    0.03us  size=     32B
  unpack (in place)                mean=    0.02us  p50=    0.02us  p99=    0.02us  size=     32B
```

## bench_ringbuffer.nim (cross-process shared memory)
```
=== Nim SPSC ring buffer, cross-process (fork), N=500000 ===
  received 500000 messages in 0.0049s  (102017706. msg/s)
```

## bench_flatbuffers.nim (Nim calling the C++ FlatBuffers library)
```

=== Nim -> C++ FlatBuffers IMU batch (n=20 samples/msg) ===
  build (Nim -> C++ FlatBufferBuilder) mean=    0.11us  p50=    0.11us  p99=    0.19us  size=    664B
  read+sum (zero-copy, C++ accessors) mean=    0.04us  p50=    0.04us  p99=    0.04us  size=    664B

=== Nim -> C++ FlatBuffers IMU batch (n=1 samples/msg) ===
  build (Nim -> C++ FlatBufferBuilder) mean=    0.06us  p50=    0.06us  p99=    0.08us  size=     56B
  read+sum (zero-copy, C++ accessors) mean=    0.03us  p50=    0.03us  p99=    0.03us  size=     56B

=== Nim -> C++ FlatBuffers LaserScan (n=1080 points) ===
  build (from seq[float32])        mean=    0.15us  p50=    0.15us  p99=    0.18us  size=   4392B
  read+sum (all elements)          mean=    0.63us  p50=    0.63us  p99=    0.63us  size=   4392B

=== Nim -> C++ FlatBuffers LaserScan (n=2000 points) ===
  build (from seq[float32])        mean=    0.19us  p50=    0.18us  p99=    0.25us  size=   8072B
  read+sum (all elements)          mean=    1.15us  p50=    1.14us  p99=    1.15us  size=   8072B
```
