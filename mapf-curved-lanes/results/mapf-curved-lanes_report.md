# mapf-curved-lanes benchmark report

Generated: 2026-08-08 04:02:57 UTC

## Hardware
```
vCPUs: 4
               total        used        free      shared  buff/cache   available
Mem:            15Gi       1.0Gi        11Gi        47Mi       3.2Gi        14Gi
Swap:          3.0Gi          0B       3.0Gi
Python 3.12.13
```

## Unit tests
```
============================= test session starts ==============================
platform linux -- Python 3.12.13, pytest-9.1.1, pluggy-1.6.0 -- /opt/hostedtoolcache/Python/3.12.13/x64/bin/python3
cachedir: .pytest_cache
benchmark: 5.2.3 (defaults: timer=time.perf_counter disable_gc=False min_rounds=5 min_time=0.000005 max_time=1.0 calibration_precision=10 warmup=False warmup_iterations=100000)
rootdir: /home/runner/work/cc-code/cc-code/mapf-curved-lanes
plugins: cov-7.1.0, benchmark-5.2.3, asyncio-1.4.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 8 items

tests/test_conflict_tree.py::test_cbs_resolves_head_on_conflict PASSED   [ 12%]
tests/test_conflict_tree.py::test_pbs_resolves_head_on_conflict PASSED   [ 25%]
tests/test_conflict_tree.py::test_invalid_mode_raises PASSED             [ 37%]
tests/test_lane_graph.py::test_straight_segment_pose_at PASSED           [ 50%]
tests/test_lane_graph.py::test_curved_segment_quarter_circle PASSED      [ 62%]
tests/test_lane_graph.py::test_pose_at_out_of_range_raises PASSED        [ 75%]
tests/test_lane_graph.py::test_graph_add_and_neighbors PASSED            [ 87%]
tests/test_lane_graph.py::test_graph_validate_catches_missing_node PASSED [100%]

============================== 8 passed in 0.11s ===============================
```

## Instance generation (the only end-to-end runnable pipeline stage)

```
wrote small_medium_a10_m50-50_000
wrote small_medium_a10_m50-50_001
wrote small_medium_a10_m50-50_002
  (small map, 10 agents, 3 instances: 0.131s)
wrote small_medium_a25_m50-50_000
wrote small_medium_a25_m50-50_001
wrote small_medium_a25_m50-50_002
  (small map, 25 agents, 3 instances: 0.129s)
wrote small_medium_a50_m50-50_000
wrote small_medium_a50_m50-50_001
wrote small_medium_a50_m50-50_002
  (small map, 50 agents, 3 instances: 0.130s)
wrote medium_medium_a10_m50-50_000
wrote medium_medium_a10_m50-50_001
wrote medium_medium_a10_m50-50_002
  (medium map, 10 agents, 3 instances: 0.135s)
wrote medium_medium_a25_m50-50_000
wrote medium_medium_a25_m50-50_001
wrote medium_medium_a25_m50-50_002
  (medium map, 25 agents, 3 instances: 0.133s)
wrote medium_medium_a50_m50-50_000
wrote medium_medium_a50_m50-50_001
wrote medium_medium_a50_m50-50_002
  (medium map, 50 agents, 3 instances: 0.134s)
wrote large_medium_a10_m50-50_000
wrote large_medium_a10_m50-50_001
wrote large_medium_a10_m50-50_002
  (large map, 10 agents, 3 instances: 0.187s)
wrote large_medium_a25_m50-50_000
wrote large_medium_a25_m50-50_001
wrote large_medium_a25_m50-50_002
  (large map, 25 agents, 3 instances: 0.192s)
wrote large_medium_a50_m50-50_000
wrote large_medium_a50_m50-50_001
wrote large_medium_a50_m50-50_002
  (large map, 50 agents, 3 instances: 0.189s)
```

## Solver status (honesty check, not a benchmark)

The high-level conflict-tree search (`src/high_level/conflict_tree.py`) and the
lane-graph geometry/conflict layer (`src/lane_graph/`) are implemented and covered
by the unit tests above. The per-agent-class low-level planners
(`src/planners/forklift_planner.py`, `src/planners/quadruped_planner.py`) and the
junction swept-volume conflict checker
(`src/lane_graph/conflicts.py::JunctionConflictChecker`) currently raise
`NotImplementedError`. There is therefore no solver-level result to compare
against the CL-CBS / HCBS baselines described in `docs/benchmark_plan.md` yet --
that comparison is the next milestone, not something this report claims to have.
