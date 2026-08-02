# bench_flatbuffers.nim
# Calls the real C++ FlatBuffers library (via flatbuffer_shim.hpp)
# directly from Nim using {.importcpp.} -- this is Nim/C++ interop in
# practice, not a Nim reimplementation of the FlatBuffers format.

import std/os

{.passC: "-I" & currentSourcePath().parentDir().}

import std/[times, monotimes, algorithm, sequtils, strformat, random]

type ImuBatchHandle {.importcpp: "ImuBatchHandle", header: "flatbuffer_shim.hpp".} = object
type LaserScanBuilderHandle {.importcpp: "LaserScanBuilderHandle", header: "flatbuffer_shim.hpp".} = object

proc imuBuilderNew(): ptr ImuBatchHandle {.importcpp: "imu_builder_new()", header: "flatbuffer_shim.hpp".}
proc imuBuild(b: ptr ImuBatchHandle, ts: ptr float64, accelGyro: ptr float32, n: cint): csize_t
  {.importcpp: "imu_build(@)", header: "flatbuffer_shim.hpp".}
proc imuBuilderData(b: ptr ImuBatchHandle): ptr uint8
  {.importcpp: "imu_builder_data(@)", header: "flatbuffer_shim.hpp".}
proc imuReadSum(buf: ptr uint8): float32 {.importcpp: "imu_read_sum(@)", header: "flatbuffer_shim.hpp".}

proc laserBuilderNew(nPoints: cint): ptr LaserScanBuilderHandle
  {.importcpp: "laser_builder_new(@)", header: "flatbuffer_shim.hpp".}
proc laserBuild(b: ptr LaserScanBuilderHandle, ts: uint64, angleMin, angleMax, angleInc,
                 rangeMin, rangeMax: float32, ranges: ptr float32, n: cint): csize_t
  {.importcpp: "laser_build(@)", header: "flatbuffer_shim.hpp".}
proc laserBuilderData(b: ptr LaserScanBuilderHandle): ptr uint8
  {.importcpp: "laser_builder_data(@)", header: "flatbuffer_shim.hpp".}
proc laserReadSum(buf: ptr uint8): float32 {.importcpp: "laser_read_sum(@)", header: "flatbuffer_shim.hpp".}

proc nowNs(): int64 = getMonoTime().ticks

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

proc benchImu(n: int, iters: int) =
  echo &"\n=== Nim -> C++ FlatBuffers IMU batch (n={n} samples/msg) ==="
  var ts = newSeq[float64](n)
  var ag = newSeq[float32](n * 6)
  for i in 0 ..< n:
    ts[i] = i.float64
    ag[i*6+0] = 0.1; ag[i*6+1] = 0.2; ag[i*6+2] = 9.81
    ag[i*6+3] = 0.01; ag[i*6+4] = 0.02; ag[i*6+5] = 0.03

  let builder = imuBuilderNew()
  var lastSize: csize_t
  let s1 = timed(proc() =
    lastSize = imuBuild(builder, addr ts[0], addr ag[0], n.cint)
  , iters)
  printRow("build (Nim -> C++ FlatBufferBuilder)", s1, lastSize.int)

  var sink: float32 = 0
  let s2 = timed(proc() =
    sink += imuReadSum(imuBuilderData(builder))
  , iters)
  printRow("read+sum (zero-copy, C++ accessors)", s2, lastSize.int)
  if sink == 0.0: echo "unreachable"  # keep `sink` observably used

proc benchLaserScan(nPoints: int, iters: int) =
  echo &"\n=== Nim -> C++ FlatBuffers LaserScan (n={nPoints} points) ==="
  var rng = initRand(42)
  var ranges = newSeq[float32](nPoints)
  for i in 0 ..< nPoints: ranges[i] = rng.rand(0.05 .. 25.0)

  let builder = laserBuilderNew(nPoints.cint)
  var lastSize: csize_t
  let s1 = timed(proc() =
    lastSize = laserBuild(builder, 1'u64, -3.14, 3.14, 0.0058, 0.05, 30.0,
                           addr ranges[0], nPoints.cint)
  , iters)
  printRow("build (from seq[float32])", s1, lastSize.int)

  var sink: float32 = 0
  let s2 = timed(proc() =
    sink += laserReadSum(laserBuilderData(builder))
  , iters)
  printRow("read+sum (all elements)", s2, lastSize.int)
  if sink == 0.0: echo "unreachable"

benchImu(20, 100_000)
benchImu(1, 200_000)
benchLaserScan(1080, 50_000)
benchLaserScan(2000, 30_000)
