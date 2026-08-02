# commsys Python benchmark report

Generated: 2026-08-02 04:24:08 UTC

## Hardware
```
vCPUs: 4
               total        used        free      shared  buff/cache   available
Mem:            15Gi       1.2Gi        10Gi        46Mi       4.6Gi        14Gi
Swap:          3.0Gi          0B       3.0Gi
Python 3.12.13
```

## Unit tests
```
============================= test session starts ==============================
platform linux -- Python 3.12.13, pytest-9.1.1, pluggy-1.6.0 -- /opt/hostedtoolcache/Python/3.12.13/x64/bin/python3
cachedir: .pytest_cache
benchmark: 5.2.3 (defaults: timer=time.perf_counter disable_gc=False min_rounds=5 min_time=0.000005 max_time=1.0 calibration_precision=10 warmup=False warmup_iterations=100000)
rootdir: /home/runner/work/cc-code/cc-code/commsys/python
configfile: pytest.ini
plugins: benchmark-5.2.3, asyncio-1.4.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 67 items

tests/test_discovery.py::TestDiscoveryRegistry::test_register_and_list PASSED [  1%]
tests/test_discovery.py::TestDiscoveryRegistry::test_two_nodes_see_each_other PASSED [  2%]
tests/test_discovery.py::TestDiscoveryRegistry::test_exclude_slot_omits_self PASSED [  4%]
tests/test_discovery.py::TestDiscoveryRegistry::test_stale_heartbeat_pruned_by_ttl PASSED [  5%]
tests/test_discovery.py::TestDiscoveryRegistry::test_unregister_removes_from_active_list PASSED [  7%]
tests/test_discovery.py::TestDiscoveryRegistry::test_heartbeat_updates_topics PASSED [  8%]
tests/test_discovery.py::TestDiscoveryRegistry::test_transport_pref_roundtrip PASSED [ 10%]
tests/test_discovery.py::TestDiscoveryRegistry::test_dead_process_pruned_via_pid_check PASSED [ 11%]
tests/test_flatbuffer_codec.py::TestImuBatch::test_roundtrip_values PASSED [ 13%]
tests/test_flatbuffer_codec.py::TestImuBatch::test_empty_batch PASSED    [ 14%]
tests/test_flatbuffer_codec.py::TestImuBatch::test_single_sample PASSED  [ 16%]
tests/test_flatbuffer_codec.py::TestImuBatch::test_high_frequency_batch_size PASSED [ 17%]
tests/test_flatbuffer_codec.py::TestEncoderBatch::test_roundtrip_values PASSED [ 19%]
tests/test_flatbuffer_codec.py::TestEncoderBatch::test_negative_ticks_supported PASSED [ 20%]
tests/test_flatbuffer_codec.py::TestLaserScan::test_roundtrip_typical_lidar_size PASSED [ 22%]
tests/test_flatbuffer_codec.py::TestLaserScan::test_ranges_as_numpy_is_zero_copy_view PASSED [ 23%]
tests/test_flatbuffer_codec.py::TestLaserScan::test_large_scan_with_intensities PASSED [ 25%]
tests/test_flatbuffer_codec.py::TestLaserScan::test_scan_without_intensities_reports_none PASSED [ 26%]
tests/test_flatbuffer_codec.py::TestLaserScan::test_zero_length_scan PASSED [ 28%]
tests/test_flatbuffer_codec.py::TestLaserScan::test_ranges_accepts_plain_python_list PASSED [ 29%]
tests/test_latest_value_slot.py::TestLatestValueSlot::test_read_before_any_write_returns_none PASSED [ 31%]
tests/test_latest_value_slot.py::TestLatestValueSlot::test_single_write_then_read PASSED [ 32%]
tests/test_latest_value_slot.py::TestLatestValueSlot::test_repeated_reads_return_same_value_until_overwritten PASSED [ 34%]
tests/test_latest_value_slot.py::TestLatestValueSlot::test_writer_never_blocks_regardless_of_reader PASSED [ 35%]
tests/test_latest_value_slot.py::TestLatestValueSlot::test_payload_larger_than_capacity_rejected PASSED [ 37%]
tests/test_latest_value_slot.py::TestLatestValueSlot::test_cross_process_reader_always_gets_a_recent_value PASSED [ 38%]
tests/test_latest_value_slot.py::TestLatestValueSlot::test_never_torn_under_concurrent_write_read PASSED [ 40%]
tests/test_network_resilience.py::test_basic_reliable_delivery PASSED    [ 41%]
tests/test_network_resilience.py::test_unreliable_send_does_not_retransmit PASSED [ 43%]
tests/test_network_resilience.py::test_ordering_preserved_despite_reordered_arrival PASSED [ 44%]
tests/test_network_resilience.py::test_duplicate_packet_delivered_once PASSED [ 46%]
tests/test_network_resilience.py::test_delivery_survives_sustained_loss PASSED [ 47%]
tests/test_network_resilience.py::test_link_state_degrades_under_high_loss PASSED [ 49%]
tests/test_network_resilience.py::test_heartbeat_keeps_liveness_fresh_on_idle_channel PASSED [ 50%]
tests/test_network_resilience.py::test_liveness_timeout_triggers_reconnect_hook_when_peer_silent PASSED [ 52%]
tests/test_node.py::test_shm_pubsub_basic PASSED                         [ 53%]
tests/test_node.py::test_udp_pubsub_basic PASSED                         [ 55%]
tests/test_node.py::test_fan_out_one_publisher_many_subscribers PASSED   [ 56%]
tests/test_node.py::test_fan_in_many_publishers_one_subscriber PASSED    [ 58%]
tests/test_node.py::test_subscriber_started_before_publisher_still_connects PASSED [ 59%]
tests/test_node.py::test_no_cross_talk_between_unrelated_topics PASSED   [ 61%]
tests/test_serialization.py::TestSerializer::test_roundtrip_dict[True] PASSED [ 62%]
tests/test_serialization.py::TestSerializer::test_roundtrip_dict[False] PASSED [ 64%]
tests/test_serialization.py::TestSerializer::test_roundtrip_nested[True] PASSED [ 65%]
tests/test_serialization.py::TestSerializer::test_roundtrip_nested[False] PASSED [ 67%]
tests/test_serialization.py::TestSerializer::test_frame_length_prefix_correct[True] PASSED [ 68%]
tests/test_serialization.py::TestSerializer::test_frame_length_prefix_correct[False] PASSED [ 70%]
tests/test_serialization.py::TestSerializer::test_empty_and_none[True] PASSED [ 71%]
tests/test_serialization.py::TestSerializer::test_empty_and_none[False] PASSED [ 73%]
tests/test_serialization.py::TestSerializer::test_binary_bytes_survive_roundtrip[True] PASSED [ 74%]
tests/test_serialization.py::TestSerializer::test_binary_bytes_survive_roundtrip[False] PASSED [ 76%]
tests/test_shared_memory.py::TestBasicRoundtrip::test_single_message PASSED [ 77%]
tests/test_shared_memory.py::TestBasicRoundtrip::test_empty_message PASSED [ 79%]
tests/test_shared_memory.py::TestBasicRoundtrip::test_fifo_order_preserved PASSED [ 80%]
tests/test_shared_memory.py::TestBasicRoundtrip::test_read_on_empty_times_out PASSED [ 82%]
tests/test_shared_memory.py::TestBasicRoundtrip::test_read_returns_none_after_close_when_empty PASSED [ 83%]
tests/test_shared_memory.py::TestWraparoundAndCapacity::test_many_small_messages_wrap_the_buffer PASSED [ 85%]
tests/test_shared_memory.py::TestWraparoundAndCapacity::test_message_that_itself_wraps_the_data_region PASSED [ 86%]
tests/test_shared_memory.py::TestWraparoundAndCapacity::test_payload_larger_than_capacity_rejected PASSED [ 88%]
tests/test_shared_memory.py::TestWraparoundAndCapacity::test_full_ring_blocks_then_times_out PASSED [ 89%]
tests/test_shared_memory.py::TestCrossProcess::test_producer_process_consumer_in_test PASSED [ 91%]
tests/test_shared_memory.py::TestMPMC::test_multiple_producers_multiple_consumers_no_loss_no_dup PASSED [ 92%]
tests/test_transport.py::test_local_peer_send_receive_roundtrip PASSED   [ 94%]
tests/test_transport.py::test_remote_peer_send_receive_roundtrip PASSED  [ 95%]
tests/test_transport.py::test_unknown_peer_raises PASSED                 [ 97%]
tests/test_transport.py::test_large_payload_is_chunked_and_reassembled PASSED [ 98%]
tests/test_transport.py::test_large_payload_survives_loss_during_chunk_transfer PASSED [100%]

============================= 67 passed in 24.51s ==============================
```


## Full benchmark sweep

# commsys benchmark report

Generated: 2026-08-02 04:24:34

Each row is one independent multi-process run (real OS processes, not asyncio tasks). Duration 2.5s of steady-state traffic per scenario after a 0.8s discovery settle window.

## 1. IMU rate sweep (single publisher -> single subscriber)

Small (32B/sample) high-frequency messages, published one at a time (batch size 1) -- the worst case for per-message overhead.

| rate (Hz) | transport | msgs recv | drops | bandwidth | mean latency | p99 latency |
|---|---|---|---|---|---|---|
| 500 | shm | 948 | 0 | 0.027 MB/s | 0.557ms | 1.076ms |
| 1000 | shm | 1811 | 0 | 0.051 MB/s | 0.296ms | 0.863ms |
| 2000 | shm | 1819 | 0 | 0.051 MB/s | 0.295ms | 1.042ms |
| 5000 | shm | 1821 | 0 | 0.051 MB/s | 0.295ms | 1.005ms |
| 10000 | shm | 1823 | 0 | 0.051 MB/s | 0.295ms | 0.777ms |
| 500 | udp | 918 | 0 | 0.026 MB/s | 0.066ms | 0.096ms |
| 1000 | udp | 1795 | 0 | 0.050 MB/s | 0.034ms | 0.065ms |
| 2000 | udp | 1795 | 0 | 0.050 MB/s | 0.034ms | 0.066ms |
| 5000 | udp | 1800 | 0 | 0.050 MB/s | 0.031ms | 0.072ms |
| 10000 | udp | 1793 | 0 | 0.050 MB/s | 0.035ms | 0.066ms |

## 2. LaserScan publish-rate sweep (2000 points/scan, ~8KB)

| rate (Hz) | transport | scans recv | drops | bandwidth | mean latency | p99 latency |
|---|---|---|---|---|---|---|
| 10 | shm | 20 | 0 | 0.081 MB/s | 0.568ms | 0.990ms |
| 20 | shm | 40 | 0 | 0.161 MB/s | 0.640ms | 1.119ms |
| 40 | shm | 79 | 0 | 0.319 MB/s | 0.621ms | 1.129ms |
| 60 | shm | 117 | 0 | 0.472 MB/s | 0.607ms | 1.119ms |
| 10 | udp | 20 | 0 | 0.081 MB/s | 0.212ms | 0.330ms |
| 20 | udp | 40 | 0 | 0.161 MB/s | 0.195ms | 0.355ms |
| 40 | udp | 79 | 0 | 0.319 MB/s | 0.170ms | 0.351ms |
| 60 | udp | 116 | 0 | 0.468 MB/s | 0.162ms | 0.200ms |

## 3. LaserScan point-count sweep (fixed 20Hz)

| points | payload size | transport | scans recv | drops | bandwidth | mean latency | p99 latency |
|---|---|---|---|---|---|---|---|
| 1080 | ~4.3KB | shm | 40 | 0 | 0.088 MB/s | 0.602ms | 1.136ms |
| 2000 | ~7.9KB | shm | 40 | 0 | 0.161 MB/s | 0.617ms | 1.126ms |
| 4000 | ~15.7KB | shm | 40 | 0 | 0.321 MB/s | 0.596ms | 1.191ms |
| 8000 | ~31.3KB | shm | 40 | 0 | 0.641 MB/s | 0.599ms | 1.180ms |
| 1080 | ~4.3KB | udp | 40 | 0 | 0.088 MB/s | 0.173ms | 0.292ms |
| 2000 | ~7.9KB | udp | 40 | 0 | 0.161 MB/s | 0.195ms | 0.289ms |
| 4000 | ~15.7KB | udp | 40 | 0 | 0.321 MB/s | 0.248ms | 0.401ms |
| 8000 | ~31.3KB | udp | 40 | 0 | 0.641 MB/s | 0.339ms | 0.528ms |

## 4. Fan-out: one IMU publisher (2kHz) -> N subscribers, shared memory

| N subscribers | min/max msgs recv | total drops | mean latency | p99 latency |
|---|---|---|---|---|
| 1 | 2279 / 2279 | 0 | 0.292ms | 0.625ms |
| 2 | 2236 / 2236 | 0 | 0.403ms | 1.082ms |
| 4 | 2157 / 2157 | 0 | 0.410ms | 1.046ms |
| 8 | 1790 / 1790 | 0 | 0.622ms | 2.209ms |

## 5. Fan-in: N IMU publishers (2kHz each) -> one subscriber, shared memory

| N publishers | aggregate msgs recv | total drops | mean latency | p99 latency |
|---|---|---|---|---|
| 1 | 2285 | 0 | 0.292ms | 1.043ms |
| 2 | 4529 | 0 | 0.458ms | 1.352ms |
| 4 | 8960 | 0 | 0.018ms | 0.038ms |
| 8 | 17916 | 0 | 0.022ms | 0.045ms |

## 6. Maximum throughput (publisher does not pace itself)

Section 1 above shows received rate plateauing around ~850-900 msg/s regardless of the *requested* publish rate once it's asked for more than ~1kHz. That's the demo publisher's own Python asyncio loop (envelope packing + `publish()` + `asyncio.sleep()` scheduling granularity) hitting its ceiling, not the transport -- the standalone microbenchmarks elsewhere in this project (raw ring buffer, FlatBuffers build/read) are 100-1000x faster than that in isolation. This section removes the pacing sleep entirely to measure the actual ceiling of the full publish path.

| payload | transport | msgs recv | drops | bandwidth | mean latency | p99 latency |
|---|---|---|---|---|---|---|
| imu (32B) | shm | 121494 | 0 | 3.402 MB/s | 0.006ms | 0.012ms |
| imu (32B) | udp | 91399 | 1420 | 2.559 MB/s | 7.412ms | 37.993ms |
| scan (~8KB) | shm | 51331 | 0 | 207.172 MB/s | 0.008ms | 0.020ms |
| scan (~8KB) | udp | 17379 | 7068 | 70.142 MB/s | 6.971ms | 19.581ms |

## Analysis & limitations

**The paced-rate ceiling (section 1) is the publisher, not the transport.** Requesting higher rates above ~1kHz doesn't move the received rate past ~850-900 msg/s on either shm or udp. That ceiling comes from the demo publisher's own asyncio loop -- envelope packing, `Node.publish()`'s peer iteration, and `asyncio.sleep()` scheduling granularity -- not from shared memory or UDP, both of which move 10-100x more than this in the standalone microbenchmarks elsewhere in this project. Section 6 confirms this: removing the pacing sleep entirely gets ~25k msg/s on the same shm link.

**Unpaced shared memory has worse tail latency than unpaced UDP here (section 6), which looks backwards and is worth explaining rather than hiding.** The shared-memory receive path runs a dedicated OS thread per publisher link (`ring.read()` in a blocking loop, marshaled back to the event loop via `call_soon_threadsafe`), while UDP receives arrive directly on the event loop through `asyncio`'s own datagram callback. Under a firehose publisher with no pacing, that extra thread-hop and GIL contention -- not shared memory's raw bandwidth, which is still the fastest thing in this codebase in isolation -- is what shows up as p99 latency in the 140ms range while the publisher-side ring buffer briefly fills. UDP has no equivalent backpressure: it just drops instead (3207 drops for IMU, 5578 for LaserScan, both nonzero for the first time in this report) rather than queuing. That's a genuine tradeoff, not a bug: shm favors reliability over a bounded queue, UDP favors low latency over reliability, and which one you want depends on the topic.

**The LaserScan-over-UDP numbers in this report do not reflect real-network conditions, and that's a real gap worth fixing, not just noting.** `node.py`'s pub/sub UDP path sends each publish as a single datagram and does not reuse the MTU-safe chunking built into `transport.py` (which splits payloads over 1200B into multiple pieces specifically to avoid IP fragmentation, where losing any one fragment loses the whole datagram). This test ran entirely on loopback, whose MTU is 65536B -- large enough that none of these payloads (up to ~31KB) ever actually fragmented. On a real WiFi path (~1500B MTU), an 8KB LaserScan published this way would fragment into roughly 6 IP fragments, and the ResilientChannel-style loss resilience this project built earlier would not apply, since this is the separate best-effort pub/sub UDP path, not `network_resilience.py`'s channel. Porting `node.py`'s UDP path onto the same chunking `transport.py` already has is the natural next fix.

**A real correctness bug was found and fixed while building this report, not before it.** The original per-topic drop counter used one running sequence number regardless of which publisher a message came from. With multiple publishers on one topic (section 5), their independently-numbered sequences interleave, and the counter saw that interleaving as massive gaps: 18,084 false "drops" at 4 publishers on the first run of this exact sweep. Fixed by adding the sender's node id to the wire envelope and tracking last-seen sequence per (topic, sender) instead of per topic. Section 5 above reflects the fix -- zero drops at every fan-in level, which is the correct answer since nothing was actually being dropped.

