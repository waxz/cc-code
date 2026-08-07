# commsys Nim benchmark report

Generated: 2026-08-07 21:01:49 UTC

## Hardware
```
vCPUs: 4
               total        used        free      shared  buff/cache   available
Mem:            15Gi       1.0Gi        11Gi        47Mi       3.2Gi        14Gi
Swap:          3.0Gi          0B       3.0Gi
Nim Compiler Version 1.6.14 [Linux: amd64]
```

## bench_struct.nim (raw struct pack/unpack)
```
=== Nim raw struct IMU batch (n=20 samples/msg) ===
  pack (copyMem)                   mean=    0.04us  p50=    0.04us  p99=    0.05us  size=    640B
  unpack+sum (in place, no copy)   mean=    0.04us  p50=    0.04us  p99=    0.05us  size=    640B

=== Nim raw struct IMU (n=1 sample/msg) ===
  pack (copyMem)                   mean=    0.03us  p50=    0.03us  p99=    0.04us  size=     32B
  unpack (in place)                mean=    0.03us  p50=    0.03us  p99=    0.04us  size=     32B
```

## bench_ringbuffer.nim (cross-process shared memory)
```
=== Nim SPSC ring buffer, cross-process (fork), N=500000 ===
  received 500000 messages in 0.0050s  (100620507. msg/s)
```

## bench_flatbuffers.nim (Nim calling the C++ FlatBuffers library)
```

=== Nim -> C++ FlatBuffers IMU batch (n=20 samples/msg) ===
  build (Nim -> C++ FlatBufferBuilder) mean=    0.17us  p50=    0.16us  p99=    0.19us  size=    664B
  read+sum (zero-copy, C++ accessors) mean=    0.05us  p50=    0.05us  p99=    0.06us  size=    664B

=== Nim -> C++ FlatBuffers IMU batch (n=1 samples/msg) ===
  build (Nim -> C++ FlatBufferBuilder) mean=    0.08us  p50=    0.08us  p99=    0.10us  size=     56B
  read+sum (zero-copy, C++ accessors) mean=    0.03us  p50=    0.03us  p99=    0.04us  size=     56B

=== Nim -> C++ FlatBuffers LaserScan (n=1080 points) ===
  build (from seq[float32])        mean=    0.26us  p50=    0.26us  p99=    0.30us  size=   4392B
  read+sum (all elements)          mean=    1.17us  p50=    1.16us  p99=    1.16us  size=   4392B

=== Nim -> C++ FlatBuffers LaserScan (n=2000 points) ===
  build (from seq[float32])        mean=    0.32us  p50=    0.31us  p99=    0.33us  size=   8072B
  read+sum (all elements)          mean=    2.14us  p50=    2.12us  p99=    2.12us  size=   8072B
```
