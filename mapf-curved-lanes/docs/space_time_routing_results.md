# Space-Time Routing: Implementation and Measured Results

This addresses `docs/weaknesses_analysis.md` section 1.1's highest-ranked
weakness: the low-level planner's wait-only constraint handling. The fix
(`src/lane_graph/space_time_routing.py`) is implemented, verified correct in
isolation, and integrated into both planners. **The honest result is mixed**:
it fixes real bugs and adds real capability (rerouting), but does not improve
this project's measured aggregate benchmark success rate, and reveals a
different, real cost. This is reported precisely rather than rounded up to a
success story.

## 1. What was built

`src/lane_graph/space_time_routing.py::space_time_search`: genuine space-time
A*, searching `(node, discretized-timestep)` states directly rather than
computing one static route and only ever inserting waits. This is exactly the
low-level search technique Sharon et al.'s original CBS paper uses, and exactly
what this project's own `src/baselines/grid_cbs.py::space_time_astar` already
did correctly on a discrete grid — the gap closed here is that the *lane-graph*
planners (`src/planners/forklift_planner.py`, `quadruped_planner.py`) never got
the same treatment.

**Verified working in isolation** (not assumed): given a graph with both a
direct route and a blocked shortcut, the search correctly detours via the
alternate route rather than waiting indefinitely for the shortcut to clear —
see the smoke test in this document's companion commit.

## 2. Two real bugs found and fixed while integrating it

1. **Zero-width conflict window treated as a violation.** The high-level
   conflict detector's boundary check (`t_overlap_start > t_overlap_end` before
   returning "no conflict") let an *exact* touch — two padded occupancies
   meeting at precisely one instant with zero overlap duration — count as a
   conflict requiring further branching. This is the safety margin being
   exactly satisfied, not violated. Found by tracing an actual non-converging
   search and watching a conflict window collapse to `t_start == t_end`, not
   by inspection. Fixed by changing the boundary check to `>=` in both
   `check_lane_conflicts` and `check_node_conflict`
   (`src/lane_graph/conflicts.py`).
2. **Needless oscillation when a node is temporarily blocked.** Without a
   tie-break, the search had no preference between waiting in place and moving
   away and back when both cost the same in the discretized model — and
   sometimes preferred bouncing, since a temporarily-blocked node genuinely can
   force an agent to be somewhere else at that instant. Each bounce creates a
   new segment-occupancy window that can trigger fresh conflicts, compounding
   convergence problems. Found by inspecting an actual returned trajectory with
   a nonsensical `[s1, s1, s1, s2]` leg sequence for a straight-line trip, not
   assumed necessary in advance. Mitigated with a small tie-break penalty on
   movement relative to waiting (`_MOVE_TIE_BREAK_EPS`).

Both are documented in place, in the code, with the specific evidence that
found them — not summarized here as if they were anticipated in advance.

## 3. The honest result: no aggregate improvement, and a real cost

Re-running the exact same benchmark sweep used in
`docs/algorithm_comparison_report.md` (32 instances: small+medium maps,
2/4/6/10 agents, seed=100):

```
                        BEFORE (wait-only)              AFTER (space-time search)
ours_full success_rate  25.00%                          25.00%   (unchanged)
ours_full avg_runtime   0.1834s                         1.3591s  (7.4x SLOWER)
ours_full avg_cost      83.04                           102.88   (24% WORSE)
```

**Success rate did not improve. Runtime got substantially worse. Solved-instance
cost quality got worse.** This is not the result that was hoped for, and it is
reported as measured, not adjusted or omitted.

## 4. Root cause of the negative result — also found by testing, not assumed

A minimal 2-agent, single-corridor (no alternate route), head-on instance —
solvable by a human in one line of reasoning ("one agent waits at the start
until the other fully clears the corridor") — **does not converge**, even at
15,000 high-level expansions (33.7 seconds wall-clock), which rules out "just
needs a bigger budget."

This is a recognized case in the MAPF literature: vanilla CBS branches on one
conflict at a time and is known to converge slowly on exactly this
"single-shared-corridor, agents must swap ends" topology without dedicated
*corridor reasoning* (special-casing this structure to branch on "who goes
first through the whole corridor" rather than one narrow window at a time) —
not implemented in this project, before or after this change.

**Why space-time search makes this worse, not better**: the old wait-only
scheme's restricted search space (one fixed route, only timing varies)
happened to avoid this pathology on this specific case essentially by luck of
having a much smaller space to search, not because it handled corridor cases
well in general (its own, different, and more common failure mode — total
incompleteness on denser instances — is exactly what motivated this work; see
`docs/benchmark_plan.md`). Real space-time search's much richer state space
gives CBS's naive one-conflict-at-a-time branching far more room to wander
without converging on precisely the adversarial topology CBS is already known
to struggle with.

`tests/test_solver.py::test_solver_head_on_corridor_with_no_detour_is_a_known_hard_case`
locks this finding in directly, asserting `not result.success` on this exact
instance — documented and understood, not silently expected to work.
`test_solver_resolves_head_on_conflict_with_detour_available_cbs` is the fair
test of what space-time search actually adds: given an alternate route, the
solver does use it.

## 5. What this means for "catch up with other algorithms"

The evidence assembled across this project's own measurements points in one
direction: **the fix is not a better low-level search for CBS — it's a
different high-level algorithm.** This project has already measured, in
`docs/algorithm_comparison_report.md`, that PIBT does not have this failure
mode on comparable instances (its reroute-every-timestep, priority-inheritance
approach has no analogous "corridor reasoning" gap in the same way, because it
never commits to a global branch-and-bound tree in the first place) — and ran
~687x faster while doing it.

**Revised recommendation, superseding `docs/improvement_plan.md`'s original
"implement PIBT as an additional `src/solver.py` mode" framing**: rather than
continuing to invest in CBS's low-level planner (this document's own result
shows real, correct engineering effort there translating to a measured
regression, not an improvement), the higher-leverage next step is adapting
PIBT's search directly to the lane-graph — reusing this document's
`space_time_search` state representation `(node, timestep)` as the substrate,
but replacing CBS's high-level conflict-tree branching with PIBT's
priority-inheritance-with-backtracking, which this project has already
verified (in the grid setting) does not get stuck the way CBS does. This is a
different, larger piece of work than what was attempted here, not a small
follow-up — flagged honestly as such rather than understated.

## 6. What was kept, and why

`space_time_search` and both bug fixes (the conflict-detector boundary
condition, the movement tie-break) were kept in the codebase rather than
reverted, for three reasons: (1) they are independently correct and verified
—rerouting genuinely works, and the zero-width-conflict fix is a real
correctness improvement to the conflict detector regardless of what search
technique uses it; (2) the `(node, timestep)` state-space design is exactly
the substrate a future PIBT-for-lane-graph implementation (§5) would need,
so this is not wasted infrastructure even though the CBS integration didn't
pay off; (3) reverting would hide a genuine, informative negative result
behind a rollback, which runs against this project's own established practice
of reporting what was actually measured.
