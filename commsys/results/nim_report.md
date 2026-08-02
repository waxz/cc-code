# commsys Nim benchmark report

Generated: 2026-08-02 02:34:42 UTC

## Hardware
```
vCPUs: 1
               total        used        free      shared  buff/cache   available
Mem:           3.9Gi       331Mi       3.3Gi       4.2Mi       475Mi       3.6Gi
Swap:             0B          0B          0B
Nim Compiler Version 1.6.14 [Linux: amd64]
```

## bench_struct.nim (raw struct pack/unpack)
```
=== Nim raw struct IMU batch (n=20 samples/msg) ===
  pack (copyMem)                   mean=    0.05us  p50=    0.04us  p99=    0.06us  size=    640B
  unpack+sum (in place, no copy)   mean=    0.04us  p50=    0.04us  p99=    0.04us  size=    640B

=== Nim raw struct IMU (n=1 sample/msg) ===
  pack (copyMem)                   mean=    0.03us  p50=    0.03us  p99=    0.04us  size=     32B
  unpack (in place)                mean=    0.03us  p50=    0.03us  p99=    0.06us  size=     32B
```

## bench_ringbuffer.nim (cross-process shared memory)
```
=== Nim SPSC ring buffer, cross-process (fork), N=500000 ===
  received 500000 messages in 0.0031s  (161205508. msg/s)
```

## bench_flatbuffers.nim (Nim calling the C++ FlatBuffers library)
```

=== Nim -> C++ FlatBuffers IMU batch (n=20 samples/msg) ===
  build (Nim -> C++ FlatBufferBuilder) mean=    0.14us  p50=    0.13us  p99=    0.20us  size=    664B
  read+sum (zero-copy, C++ accessors) mean=    0.05us  p50=    0.05us  p99=    0.05us  size=    664B

=== Nim -> C++ FlatBuffers IMU batch (n=1 samples/msg) ===
  build (Nim -> C++ FlatBufferBuilder) mean=    0.08us  p50=    0.08us  p99=    0.12us  size=     56B
  read+sum (zero-copy, C++ accessors) mean=    0.04us  p50=    0.04us  p99=    0.05us  size=     56B

=== Nim -> C++ FlatBuffers LaserScan (n=1080 points) ===
  build (from seq[float32])        mean=    0.18us  p50=    0.17us  p99=    0.22us  size=   4392B
  read+sum (all elements)          mean=    0.75us  p50=    0.69us  p99=    0.80us  size=   4392B

=== Nim -> C++ FlatBuffers LaserScan (n=2000 points) ===
  build (from seq[float32])        mean=    0.22us  p50=    0.20us  p99=    0.30us  size=   8072B
  read+sum (all elements)          mean=    1.35us  p50=    1.25us  p99=    3.37us  size=   8072B
```
