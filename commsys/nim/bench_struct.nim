# bench_struct.nim
# Raw fixed-layout IMU sample encode/decode, mirroring bench_struct.cpp
# and the Python struct.pack benchmark: same 32-byte wire layout
# (uint64 timestamp + 6x float32).

import std/[times, monotimes, algorithm, sequtils, strformat]

type
  ImuSampleRaw {.packed.} = object
    timestampNs: uint64
    ax, ay, az: float32
    gx, gy, gz: float32

static: doAssert sizeof(ImuSampleRaw) == 32

proc nowNs(): int64 =
  getMonoTime().ticks

proc timed(fn: proc(), iters: int, warmup = 50): tuple[meanUs, p50Us, p99Us: float] =
  for i in 0 ..< warmup: fn()
  var samples = newSeq[int64](iters)
  for i in 0 ..< iters:
    let t0 = nowNs()
    fn()
    samples[i] = nowNs() - t0
  samples.sort()
  let meanNs = samples.foldl(a + b, 0'i64).float / iters.float
  result = (meanNs / 1000.0, samples[iters div 2].float / 1000.0,
            samples[int(iters.float * 0.99)].float / 1000.0)

proc printRow(name: string, s: tuple[meanUs, p50Us, p99Us: float], bytes: int) =
  echo &"  {name:<32} mean={s.meanUs:8.2f}us  p50={s.p50Us:8.2f}us  p99={s.p99Us:8.2f}us  size={bytes:>7d}B"

proc main() =
  echo "=== Nim raw struct IMU batch (n=20 samples/msg) ==="
  const n = 20
  var samples: array[n, ImuSampleRaw]
  for i in 0 ..< n:
    samples[i] = ImuSampleRaw(timestampNs: i.uint64, ax: 0.1, ay: 0.2, az: 9.81,
                              gx: 0.01, gy: 0.02, gz: 0.03)

  var buf: array[n * sizeof(ImuSampleRaw), byte]

  let s1 = timed(proc() =
    copyMem(addr buf[0], addr samples[0], buf.len)
  , 200000)
  printRow("pack (copyMem)", s1, buf.len)

  var sink: float32
  let s2 = timed(proc() =
    let p = cast[ptr UncheckedArray[ImuSampleRaw]](addr buf[0])
    var total: float32 = 0
    for i in 0 ..< n: total += p[i].az
    sink = total
  , 200000)
  printRow("unpack+sum (in place, no copy)", s2, buf.len)

  echo "\n=== Nim raw struct IMU (n=1 sample/msg) ==="
  var one = ImuSampleRaw(timestampNs: 123, ax: 0.1, ay: 0.2, az: 9.81,
                          gx: 0.01, gy: 0.02, gz: 0.03)
  var buf1: array[sizeof(ImuSampleRaw), byte]

  let s3 = timed(proc() =
    copyMem(addr buf1[0], addr one, sizeof(one))
  , 300000)
  printRow("pack (copyMem)", s3, sizeof(one))

  let s4 = timed(proc() =
    let p = cast[ptr ImuSampleRaw](addr buf1[0])
    sink = p.az
  , 300000)
  printRow("unpack (in place)", s4, sizeof(one))

main()
