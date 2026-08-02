# bench_ringbuffer.nim
# Cross-process SPSC ring buffer over POSIX shared memory, same design
# as shared_memory_ipc.py and bench_ringbuffer.cpp (doubled-modulus
# indices), benchmarked the same way: fork a producer, parent consumes,
# time until all messages are received.

import std/[posix, atomics, monotimes, times, strformat]

const Capacity = 1 shl 20  # 1 MiB

type
  RingHeader = object
    writeIdx: Atomic[uint64]
    readIdx: Atomic[uint64]
    capacity: uint64
    closed: uint8

  RingBuffer = object
    hdr: ptr RingHeader
    data: ptr UncheckedArray[byte]
    capacity: uint64

proc initRing(base: pointer, capacity: uint64): RingBuffer =
  result.hdr = cast[ptr RingHeader](base)
  result.data = cast[ptr UncheckedArray[byte]](cast[uint](base) + sizeof(RingHeader).uint)
  result.capacity = capacity

proc setup(r: var RingBuffer, capacity: uint64) =
  r.hdr.writeIdx.store(0)
  r.hdr.readIdx.store(0)
  r.hdr.capacity = capacity
  r.hdr.closed = 0

proc writeBytes(r: var RingBuffer, pos: uint64, data: pointer, n: int) =
  let p = pos mod r.capacity
  if p.int + n <= r.capacity.int:
    copyMem(addr r.data[p.int], data, n)
  else:
    let first = r.capacity.int - p.int
    copyMem(addr r.data[p.int], data, first)
    copyMem(addr r.data[0], cast[pointer](cast[uint](data) + first.uint), n - first)

proc readBytesOut(r: var RingBuffer, pos: uint64, outp: pointer, n: int) =
  let p = pos mod r.capacity
  if p.int + n <= r.capacity.int:
    copyMem(outp, addr r.data[p.int], n)
  else:
    let first = r.capacity.int - p.int
    copyMem(outp, addr r.data[p.int], first)
    copyMem(cast[pointer](cast[uint](outp) + first.uint), addr r.data[0], n - first)

proc tryWrite(r: var RingBuffer, payload: pointer, length: uint32): bool =
  let need = 4'u64 + length.uint64
  let w = r.hdr.writeIdx.load(moRelaxed)
  let rIdx = r.hdr.readIdx.load(moAcquire)
  let used = (w - rIdx) mod (2 * r.capacity)
  if r.capacity - used < need: return false
  var lenBuf = length
  r.writeBytes(w, addr lenBuf, 4)
  r.writeBytes(w + 4, payload, length.int)
  r.hdr.writeIdx.store((w + need) mod (2 * r.capacity), moRelease)
  true

proc tryRead(r: var RingBuffer, outp: pointer, outCap: int): int =
  let w = r.hdr.writeIdx.load(moAcquire)
  let rIdx = r.hdr.readIdx.load(moRelaxed)
  if w == rIdx: return -1
  var length: uint32
  r.readBytesOut(rIdx, addr length, 4)
  r.readBytesOut(rIdx + 4, outp, length.int)
  r.hdr.readIdx.store((rIdx + 4 + length.uint64) mod (2 * r.capacity), moRelease)
  length.int

proc isClosed(r: RingBuffer): bool = r.hdr.closed == 1

proc main() =
  let totalSize = sizeof(RingHeader) + Capacity
  let name = "/nim_bench_ring"
  let fd = shm_open(name.cstring, O_CREAT or O_RDWR, 0o666)
  discard ftruncate(fd, totalSize.Off)
  let base = mmap(nil, totalSize, PROT_READ or PROT_WRITE, MAP_SHARED, fd, 0)

  var ring = initRing(base, Capacity.uint64)
  ring.setup(Capacity.uint64)

  const n = 500_000

  let pid = fork()
  if pid == 0:
    # child = producer
    let fd2 = shm_open(name.cstring, O_RDWR, 0o666)
    let base2 = mmap(nil, totalSize, PROT_READ or PROT_WRITE, MAP_SHARED, fd2, 0)
    var prod = initRing(base2, Capacity.uint64)
    for i in 0 ..< n:
      var payload = i.int64
      while not prod.tryWrite(addr payload, sizeof(payload).uint32):
        discard sched_yield()
    prod.hdr.closed = 1
    quit(0)

  # parent = consumer
  var outBuf: array[64, byte]
  var received = 0
  let t0 = getMonoTime()
  while received < n:
    let got = ring.tryRead(addr outBuf[0], outBuf.len)
    if got < 0:
      if ring.isClosed: break
      discard sched_yield()
      continue
    doAssert got == sizeof(int64)
    received.inc

  let t1 = getMonoTime()
  var status: cint
  discard waitpid(pid, status, 0)

  let secs = (t1 - t0).inNanoseconds.float / 1e9
  echo &"=== Nim SPSC ring buffer, cross-process (fork), N={n} ==="
  echo &"  received {received} messages in {secs:.4f}s  ({received.float/secs:.0f} msg/s)"

  discard munmap(base, totalSize)
  discard shm_unlink(name.cstring)

main()
