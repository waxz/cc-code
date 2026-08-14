# mapf-curved-lanes benchmark report

Generated: 2026-08-14 16:45:24 UTC

## Hardware
```
vCPUs: 4
               total        used        free      shared  buff/cache   available
Mem:            15Gi       1.1Gi       9.5Gi        49Mi       5.4Gi        14Gi
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
collecting ... collected 38 items

tests/test_conflict_tree.py::test_cbs_resolves_head_on_conflict PASSED   [  2%]
tests/test_conflict_tree.py::test_pbs_resolves_head_on_conflict PASSED   [  5%]
tests/test_conflict_tree.py::test_invalid_mode_raises PASSED             [  7%]
tests/test_flatland_smoke.py::test_flatland_installs_and_runs_headless PASSED [ 10%]
tests/test_grid_cbs.py::test_grid_cbs_resolves_swap_with_room_to_pass PASSED [ 13%]
tests/test_grid_cbs.py::test_grid_cbs_infeasible_swap_in_single_width_corridor PASSED [ 15%]
tests/test_grid_cbs.py::test_instance_to_grid_snaps_nodes_to_cells PASSED [ 18%]
tests/test_lane_graph.py::test_straight_segment_pose_at PASSED           [ 21%]
tests/test_lane_graph.py::test_curved_segment_quarter_circle PASSED      [ 23%]
tests/test_lane_graph.py::test_pose_at_out_of_range_raises PASSED        [ 26%]
tests/test_lane_graph.py::test_graph_add_and_neighbors PASSED            [ 28%]
tests/test_lane_graph.py::test_graph_validate_catches_missing_node PASSED [ 31%]
tests/test_lane_graph.py::test_astar_heuristic_matches_dijkstra_on_lane_graph PASSED [ 34%]
tests/test_pibt.py::test_pibt_resolves_swap_with_room_to_pass PASSED     [ 36%]
tests/test_pibt.py::test_pibt_does_not_deadlock_on_head_on_corridor_with_no_detour PASSED [ 39%]
tests/test_pibt.py::test_pibt_freezes_agents_at_goal_instead_of_oscillating PASSED [ 42%]
tests/test_pibt.py::test_pibt_collision_free_across_many_random_instances PASSED [ 44%]
tests/test_pibt.py::test_dynamic_priority_matches_static_on_small_instance_corpus PASSED [ 47%]
tests/test_proving.py::test_framework_catches_the_seeded_bug PASSED      [ 50%]
tests/test_proving.py::test_shrinker_reduces_seeded_bug_to_minimal_diagonal_counterexample PASSED [ 52%]
tests/test_proving.py::test_dijkstra_and_astar_agree_on_many_random_instances PASSED [ 55%]
tests/test_proving.py::test_jps_and_matching_dijkstra_agree_on_many_random_instances PASSED [ 57%]
tests/test_proving.py::test_mapf_solver_self_consistency_on_random_instances PASSED [ 60%]
tests/test_single_agent.py::test_load_map_parses_dimensions_and_passability PASSED [ 63%]
tests/test_single_agent.py::test_load_scen_parses_known_entry_count_and_fields PASSED [ 65%]
tests/test_single_agent.py::test_dijkstra_and_astar_match_known_optimal_on_real_scenarios PASSED [ 68%]
tests/test_single_agent.py::test_astar_expands_fewer_or_equal_nodes_than_dijkstra PASSED [ 71%]
tests/test_single_agent.py::test_jps_self_consistent_with_matching_corner_cutting_dijkstra_fuzz PASSED [ 73%]
tests/test_single_agent.py::test_jps_self_consistent_on_real_scenarios PASSED [ 76%]
tests/test_single_agent.py::test_unreachable_goal_returns_no_path PASSED [ 78%]
tests/test_single_agent.py::test_corner_cutting_is_prevented PASSED      [ 81%]
tests/test_solver.py::test_load_dependent_curvature_changes_route PASSED [ 84%]
tests/test_solver.py::test_curved_segment_speed_is_capped_so_margin_never_negative PASSED [ 86%]
tests/test_solver.py::test_infeasible_when_only_route_exceeds_curvature_bound_for_both_states PASSED [ 89%]
tests/test_solver.py::test_solver_resolves_head_on_conflict_with_detour_available_cbs PASSED [ 92%]
tests/test_solver.py::test_solver_head_on_corridor_with_no_detour_is_a_known_hard_case PASSED [ 94%]
tests/test_solver.py::test_solver_resolves_head_on_conflict_pbs PASSED   [ 97%]
tests/test_solver.py::test_solver_heterogeneous_fleet_no_conflict_when_independent PASSED [100%]

============================= 38 passed in 23.83s ==============================
```

## Single-agent global planner benchmark (real MovingAI dataset)

See `docs/single_agent_benchmark.md` for the full writeup -- this is the
foundation the multi-agent low-level planners' routing
(`src/lane_graph/routing.py`) is built on and was benchmarked against.

```
=== Single-agent benchmark summary (random-32-32-20, MovingAI) ===
astar      n= 409  success_rate=100.00%  avg_nodes_expanded=    69.6  avg_runtime=0.273ms
dijkstra   n= 409  success_rate=100.00%  avg_nodes_expanded=   397.0  avg_runtime=1.169ms
jps        n= 409  self_consistent_rate=100.00%  avg_nodes_expanded=    25.0  avg_runtime=0.245ms
astar reduces total nodes expanded by 82.5% vs. dijkstra (162365 -> 28448), at identical solution cost (both optimal)
jps reduces total nodes expanded by 64.1% vs. astar (28448 -> 10221) -- different cost model (corner-cutting allowed), so not a same-cost comparison: jps cost equals the benchmark's stricter no-cut optimal on 77/409 scenarios and is strictly lower (a corner shortcut exists) on 332/409

wrote /home/runner/work/cc-code/cc-code/mapf-curved-lanes/results/single_agent_benchmark.csv
```

## Instance generation timing

```
wrote small_medium_a10_m50-50_000
wrote small_medium_a10_m50-50_001
wrote small_medium_a10_m50-50_002
  (small map, 10 agents, 3 instances: 0.126s)
wrote small_medium_a25_m50-50_000
wrote small_medium_a25_m50-50_001
wrote small_medium_a25_m50-50_002
  (small map, 25 agents, 3 instances: 0.128s)
wrote medium_medium_a10_m50-50_000
wrote medium_medium_a10_m50-50_001
wrote medium_medium_a10_m50-50_002
  (medium map, 10 agents, 3 instances: 0.132s)
wrote medium_medium_a25_m50-50_000
wrote medium_medium_a25_m50-50_001
wrote medium_medium_a25_m50-50_002
  (medium map, 25 agents, 3 instances: 0.134s)
wrote large_medium_a10_m50-50_000
wrote large_medium_a10_m50-50_001
wrote large_medium_a10_m50-50_002
  (large map, 10 agents, 3 instances: 0.181s)
wrote large_medium_a25_m50-50_000
wrote large_medium_a25_m50-50_001
wrote large_medium_a25_m50-50_002
  (large map, 25 agents, 3 instances: 0.179s)
```

## Solver comparison: ours_full vs. classical grid-CBS baseline

See `docs/benchmark_plan.md` for what each column means. This is a small,
CI-runtime-bounded sweep (few agents, few instances) -- not the full
benchmark sweep described in the research proposal, which would need much
more compute than a CI job budget allows.

```
  small_medium_a2_000                 ours_full  success=True  cost=    26.5 runtime=0.0005s
  small_medium_a2_000                 grid_cbs   success=False cost=       0 runtime=1.8477s
  small_medium_a2_000                 pibt       success=False cost=       0 runtime=0.0009s
  small_medium_a2_001                 ours_full  success=True  cost=    35.0 runtime=0.0003s
  small_medium_a2_001                 grid_cbs   success=True  cost=      12 runtime=0.0001s
  small_medium_a2_001                 pibt       success=True  cost=      12 runtime=0.0001s
  small_medium_a2_002                 ours_full  success=True  cost=    46.0 runtime=0.0004s
  small_medium_a2_002                 grid_cbs   success=True  cost=      12 runtime=0.0001s
  small_medium_a2_002                 pibt       success=True  cost=      18 runtime=0.0001s
  small_medium_a3_000                 ours_full  success=False cost=     0.0 runtime=1.2792s
  small_medium_a3_000                 grid_cbs   success=False cost=       0 runtime=2.0431s
  small_medium_a3_000                 pibt       success=False cost=       0 runtime=0.0011s
  small_medium_a3_001                 ours_full  success=True  cost=    65.5 runtime=0.002s
  small_medium_a3_001                 grid_cbs   success=False cost=       0 runtime=2.1239s
  small_medium_a3_001                 pibt       success=False cost=       0 runtime=0.0011s
  small_medium_a3_002                 ours_full  success=False cost=     0.0 runtime=0.5825s
  small_medium_a3_002                 grid_cbs   success=False cost=       0 runtime=0.0373s
  small_medium_a3_002                 pibt       success=False cost=       0 runtime=0.0011s
  small_medium_a4_000                 ours_full  success=False cost=     0.0 runtime=0.544s
  small_medium_a4_000                 grid_cbs   success=False cost=       0 runtime=0.2174s
  small_medium_a4_000                 pibt       success=False cost=       0 runtime=0.0016s
  small_medium_a4_001                 ours_full  success=True  cost=    63.0 runtime=0.0017s
  small_medium_a4_001                 grid_cbs   success=False cost=       0 runtime=1.1045s
  small_medium_a4_001                 pibt       success=False cost=       0 runtime=0.0012s
  small_medium_a4_002                 ours_full  success=False cost=     0.0 runtime=0.4195s
  small_medium_a4_002                 grid_cbs   success=False cost=       0 runtime=0.1272s
  small_medium_a4_002                 pibt       success=False cost=       0 runtime=0.0016s

=== Summary ===
grid_cbs    n=   9  success_rate=22.22%  avg_runtime=0.8335s  avg_cost_when_solved=12.00  avg_agents_per_second=17094.0
ours_full   n=   9  success_rate=55.56%  avg_runtime=0.3145s  avg_cost_when_solved=47.20  avg_agents_per_second=3722.4
pibt        n=   9  success_rate=22.22%  avg_runtime=0.0010s  avg_cost_when_solved=15.00  avg_agents_per_second=31324.0

wrote /home/runner/work/cc-code/cc-code/mapf-curved-lanes/results/solver_benchmark.csv
```

### Known limitation, found by running this comparison (not by inspection)

Both solvers show a real completeness gap on these small/sparse instances, for two
different reasons:

- **`ours_full`**: the low-level planners (`src/planners/forklift_planner.py`,
  `src/planners/quadruped_planner.py`) fix their route via A* once (see
  `docs/single_agent_benchmark.md` for the upgrade from plain Dijkstra) and, under
  a high-level constraint, only insert waits -- they never try an alternate route
  around a contested segment. Tracing a specific non-converging instance showed the
  search exploring hundreds of branches that all plateau at the exact same cost,
  which is the signature of a real incompleteness rather than "just needs a bigger
  expansion budget" (confirmed by re-running the same instance at 5000 expansions
  with no change). The fix is a low-level planner that treats a constraint as a
  temporarily removed edge and re-runs the search, not just a wait-insertion pass
  -- that's the clear next implementation step, not something papered over here.
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
