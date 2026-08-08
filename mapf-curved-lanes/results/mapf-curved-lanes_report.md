# mapf-curved-lanes benchmark report

Generated: 2026-08-08 15:37:47 UTC

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
collecting ... collected 17 items

tests/test_conflict_tree.py::test_cbs_resolves_head_on_conflict PASSED   [  5%]
tests/test_conflict_tree.py::test_pbs_resolves_head_on_conflict PASSED   [ 11%]
tests/test_conflict_tree.py::test_invalid_mode_raises PASSED             [ 17%]
tests/test_grid_cbs.py::test_grid_cbs_resolves_swap_with_room_to_pass PASSED [ 23%]
tests/test_grid_cbs.py::test_grid_cbs_infeasible_swap_in_single_width_corridor PASSED [ 29%]
tests/test_grid_cbs.py::test_instance_to_grid_snaps_nodes_to_cells PASSED [ 35%]
tests/test_lane_graph.py::test_straight_segment_pose_at PASSED           [ 41%]
tests/test_lane_graph.py::test_curved_segment_quarter_circle PASSED      [ 47%]
tests/test_lane_graph.py::test_pose_at_out_of_range_raises PASSED        [ 52%]
tests/test_lane_graph.py::test_graph_add_and_neighbors PASSED            [ 58%]
tests/test_lane_graph.py::test_graph_validate_catches_missing_node PASSED [ 64%]
tests/test_solver.py::test_load_dependent_curvature_changes_route PASSED [ 70%]
tests/test_solver.py::test_curved_segment_speed_is_capped_so_margin_never_negative PASSED [ 76%]
tests/test_solver.py::test_infeasible_when_only_route_exceeds_curvature_bound_for_both_states PASSED [ 82%]
tests/test_solver.py::test_solver_resolves_head_on_conflict_cbs PASSED   [ 88%]
tests/test_solver.py::test_solver_resolves_head_on_conflict_pbs PASSED   [ 94%]
tests/test_solver.py::test_solver_heterogeneous_fleet_no_conflict_when_independent PASSED [100%]

============================== 17 passed in 0.16s ==============================
```

## Instance generation timing

```
wrote small_medium_a10_m50-50_000
wrote small_medium_a10_m50-50_001
wrote small_medium_a10_m50-50_002
  (small map, 10 agents, 3 instances: 0.124s)
wrote small_medium_a25_m50-50_000
wrote small_medium_a25_m50-50_001
wrote small_medium_a25_m50-50_002
  (small map, 25 agents, 3 instances: 0.125s)
wrote medium_medium_a10_m50-50_000
wrote medium_medium_a10_m50-50_001
wrote medium_medium_a10_m50-50_002
  (medium map, 10 agents, 3 instances: 0.128s)
wrote medium_medium_a25_m50-50_000
wrote medium_medium_a25_m50-50_001
wrote medium_medium_a25_m50-50_002
  (medium map, 25 agents, 3 instances: 0.129s)
wrote large_medium_a10_m50-50_000
wrote large_medium_a10_m50-50_001
wrote large_medium_a10_m50-50_002
  (large map, 10 agents, 3 instances: 0.192s)
wrote large_medium_a25_m50-50_000
wrote large_medium_a25_m50-50_001
wrote large_medium_a25_m50-50_002
  (large map, 25 agents, 3 instances: 0.193s)
```

## Solver comparison: ours_full vs. classical grid-CBS baseline

See `docs/benchmark_plan.md` for what each column means. This is a small,
CI-runtime-bounded sweep (few agents, few instances) -- not the full
benchmark sweep described in the research proposal, which would need much
more compute than a CI job budget allows.

```
  small_medium_a2_000                 ours_full  success=True  cost=  26.587 runtime=0.0002s
  small_medium_a2_000                 grid_cbs   success=False cost=       0 runtime=2.3207s
  small_medium_a2_001                 ours_full  success=True  cost=    35.0 runtime=0.0001s
  small_medium_a2_001                 grid_cbs   success=True  cost=      12 runtime=0.0001s
  small_medium_a2_002                 ours_full  success=True  cost=  45.833 runtime=0.0001s
  small_medium_a2_002                 grid_cbs   success=True  cost=      12 runtime=0.0002s
  small_medium_a3_000                 ours_full  success=False cost=     0.0 runtime=0.0793s
  small_medium_a3_000                 grid_cbs   success=False cost=       0 runtime=2.5748s
  small_medium_a3_001                 ours_full  success=False cost=     0.0 runtime=0.0872s
  small_medium_a3_001                 grid_cbs   success=False cost=       0 runtime=2.6175s
  small_medium_a3_002                 ours_full  success=True  cost=    39.0 runtime=0.0002s
  small_medium_a3_002                 grid_cbs   success=False cost=       0 runtime=0.0505s
  small_medium_a4_000                 ours_full  success=False cost=     0.0 runtime=0.1854s
  small_medium_a4_000                 grid_cbs   success=False cost=       0 runtime=0.2905s
  small_medium_a4_001                 ours_full  success=True  cost=    62.5 runtime=0.0002s
  small_medium_a4_001                 grid_cbs   success=False cost=       0 runtime=1.3941s
  small_medium_a4_002                 ours_full  success=False cost=     0.0 runtime=0.0688s
  small_medium_a4_002                 grid_cbs   success=False cost=       0 runtime=0.1706s

=== Summary ===
grid_cbs    n=   9  success_rate=22.22%  avg_runtime=1.0466s  avg_cost_when_solved=12.00
ours_full   n=   9  success_rate=55.56%  avg_runtime=0.0468s  avg_cost_when_solved=41.78

wrote /home/runner/work/cc-code/cc-code/mapf-curved-lanes/results/solver_benchmark.csv
```

### Known limitation, found by running this comparison (not by inspection)

Both solvers show a real completeness gap on these small/sparse instances, for two
different reasons:

- **`ours_full`**: the low-level planners (`src/planners/forklift_planner.py`,
  `src/planners/quadruped_planner.py`) fix their route via Dijkstra once and, under
  a high-level constraint, only insert waits -- they never try an alternate route
  around a contested segment. Tracing a specific non-converging instance showed the
  search exploring hundreds of branches that all plateau at the exact same cost,
  which is the signature of a real incompleteness rather than "just needs a bigger
  expansion budget" (confirmed by re-running the same instance at 5000 expansions
  with no change). The fix is a low-level planner that treats a constraint as a
  temporarily removed edge and re-runs Dijkstra, not just a wait-insertion pass --
  that's the clear next implementation step, not something papered over here.
- **`grid_cbs`**: the grid-discretization translation (`instance_to_grid`) can snap
  multiple distinct lane-graph junctions to the same coarse grid cell on a small
  map, which can make an otherwise-solvable instance spuriously harder or
  degenerate after translation. This is a limitation of the *baseline's map
  translation*, not the CBS algorithm itself -- `src/baselines/grid_cbs.py` is
  independently verified correct on hand-built swap-conflict cases (see
  `tests/test_grid_cbs.py`).

Reported success rates and costs above should be read with both caveats in mind --
they are real numbers from real runs, not fabricated, but they reflect these two
distinct known limitations rather than a clean apples-to-apples capability
comparison yet.

== unit tests + instance generation + solver comparison done ==
