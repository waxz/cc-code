"""Priority Inheritance with Backtracking (PIBT) -- Okumura, Machida, Defago,
Tamura, "Priority Inheritance with Backtracking for Iterative Multi-Agent Path
Finding," IJCAI 2019 / Artificial Intelligence 2022 (cited in
docs/related_work.md). Reproduced from the published algorithm description, not
copied from any specific codebase (the reference implementation cited by that
paper, github.com/Kei18/pibt, was not consulted).

This is the concrete first step docs/improvement_plan.md section 7 committed to:
"Reproduce PIBT itself (not just cite it) as an additional mode... on the same
MovingAI-derived instances used for the single-agent benchmark." Implemented
here for the classical 4-connected grid MAPF setting (matching
src/baselines/grid_cbs.py's cost model, so the two are directly comparable on
identical instances) rather than this project's own curved lane-graph -- see
"Known simplifications" below for exactly what that trades away.

Algorithm sketch: at each discrete timestep, agents are processed in priority
order (highest first). Each agent greedily tries to move to the neighbor cell
(or stay) that most reduces its distance to goal, among cells not already
claimed this timestep. If its preferred cell is currently occupied by a
not-yet-decided agent, that agent is recursively asked to move first
("priority inheritance") -- if it can, the original agent takes the vacated
cell; if it can't (or a cycle is detected), the original agent tries its next
candidate. Unlike CBS/PBS, there is no completeness or optimality guarantee in
general graphs; PIBT is proven complete on biconnected graphs (every pair of
adjacent nodes lies on a common cycle) -- see the cited paper's Theorem 1. Grid
maps without articulation points typically satisfy this in practice, though it
is not checked here.

Known simplifications, disclosed rather than hidden:
- Cycle detection during priority inheritance is a simple "is this agent
  currently being processed higher in the recursion stack" check, which
  prevents infinite recursion but is not the more refined deadlock-breaking
  the original paper's backtracking describes in detail.

Priority scheme: dynamic, not static -- see `_compute_dynamic_priorities`.
An earlier version used static priorities (fixed once per instance,
documented at the time as a "standard, defensible simplification" for the
one-shot setting this project uses). Comparing against a reference
implementation (Kei18/pypibt, MIT-licensed, studied for algorithmic approach
only -- not copied, this project's version below is independently written)
showed the published algorithm actually uses dynamic priorities even in the
setting closest to one-shot MAPF: an agent's priority grows by 1 every
timestep it hasn't reached its goal, and resets to a low value once it does.
This is the mechanism that gives PIBT its starvation-freedom guarantee, not
an optional extra -- adopted here rather than left as a documented gap. See
docs/pibt_dynamic_priority_results.md for the measured effect.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

Cell = Tuple[int, int]
_MOVES = [(0, 1), (0, -1), (1, 0), (-1, 0), (0, 0)]  # 4-connected + stay


@dataclass
class PIBTAgent:
    agent_id: str
    start: Cell
    goal: Cell


@dataclass
class PIBTResult:
    success: bool
    paths: Dict[str, List[Cell]] = field(default_factory=dict)
    sum_of_costs: int = 0
    makespan: int = 0
    runtime_s: float = 0.0
    timesteps_used: int = 0


def _manhattan(a: Cell, b: Cell) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _in_bounds(cell: Cell, width: int, height: int) -> bool:
    x, y = cell
    return 0 <= x < width and 0 <= y < height


def solve_pibt(
    agents: List[PIBTAgent],
    width: int,
    height: int,
    obstacles: Optional[Set[Cell]] = None,
    max_timesteps: int = 500,
    priority_seed: int = 0,
    dynamic_priority: bool = True,
) -> PIBTResult:
    """Run PIBT until every agent has reached its goal or max_timesteps is
    exhausted. Returns success=False (not a raised exception) if the timestep
    budget runs out with agents still short of their goal -- a normal, expected
    outcome for a suboptimal, non-complete-in-general-graphs algorithm, not an
    implementation error.

    dynamic_priority (default True): use the literature's starvation-free
    scheme (priority grows the longer an agent waits, resets on arrival)
    rather than a fixed priority order. Kept togglable, not because static
    priority is recommended, but so docs/pibt_dynamic_priority_results.md's
    before/after comparison can be reproduced directly by flipping one flag
    on otherwise identical code.
    """
    import random

    t0 = time.perf_counter()
    obstacles = obstacles or set()
    n = len(agents)
    ids = [a.agent_id for a in agents]
    pos: Dict[str, Cell] = {a.agent_id: a.start for a in agents}
    goal: Dict[str, Cell] = {a.agent_id: a.goal for a in agents}
    paths: Dict[str, List[Cell]] = {a.agent_id: [a.start] for a in agents}

    rng = random.Random(priority_seed)
    priority_order = ids[:]
    rng.shuffle(priority_order)
    # Initial priority value (higher = goes first). With dynamic_priority=True
    # this is only the starting point -- see the update rule at the bottom of
    # the main loop below, which is what actually gives PIBT its
    # starvation-freedom guarantee (an agent that keeps losing contested
    # cells has its priority grow every timestep until it eventually outranks
    # whatever was blocking it).
    priority_value = {aid: float(n - i) for i, aid in enumerate(priority_order)}

    # One-shot MAPF convention: once an agent reaches its goal it stays there
    # permanently for the rest of the run, rather than remaining eligible to be
    # displaced by another agent's priority-inheritance recursion. Without
    # this, an agent sitting at its own goal can be evicted by a passing
    # higher-priority agent, immediately try to return next timestep (since
    # distance 0 is always its best greedy choice), get evicted again, and
    # oscillate forever -- measured, not hypothetical: an early version of
    # this function without the freeze produced exactly that oscillation
    # (agents alternating between their goal and one neighbor, 200/200
    # timesteps, on an open grid with no obstacles at all) on 74% of random
    # small instances (tests/test_pibt.py locks this finding in as a
    # regression test).
    frozen_at_goal: Set[str] = set()

    def passable(cell: Cell) -> bool:
        return _in_bounds(cell, width, height) and cell not in obstacles

    for t in range(max_timesteps):
        if all(pos[aid] == goal[aid] for aid in ids):
            return PIBTResult(
                success=True, paths=paths,
                sum_of_costs=sum(len(paths[aid]) - 1 for aid in ids),
                makespan=max(len(paths[aid]) - 1 for aid in ids),
                runtime_s=time.perf_counter() - t0, timesteps_used=t,
            )

        occupied_by: Dict[Cell, str] = {pos[aid]: aid for aid in ids}
        decided: Dict[str, Cell] = {}
        in_progress: Set[str] = set()
        reserved_cells: Dict[Cell, str] = {}

        for aid in ids:
            if pos[aid] == goal[aid]:
                frozen_at_goal.add(aid)
        for aid in frozen_at_goal:
            decided[aid] = pos[aid]
            reserved_cells[pos[aid]] = aid

        def decide(agent_id: str) -> bool:
            if agent_id in decided:
                return agent_id in frozen_at_goal or True
            if agent_id in in_progress:
                return False  # cycle: treat as blocked for this branch
            in_progress.add(agent_id)

            here = pos[agent_id]
            g = goal[agent_id]
            moves = []
            for dx, dy in _MOVES:
                if dx == 0 and dy == 0:
                    continue  # handle "stay" separately, as an absolute last resort below
                c = (here[0] + dx, here[1] + dy)
                if passable(c):
                    moves.append(c)
            # Genuine moves first, ranked by which most reduces distance to goal.
            # "Stay" is deliberately NOT ranked among them by raw distance and
            # tried last: an earlier version sorted stay alongside moves by
            # distance-to-goal, and since staying often has a *better* raw
            # distance than a detour (you don't backtrack away from the goal to
            # take a detour), two agents blocking each other head-on would both
            # find "stay" the locally best option and neither would ever reach
            # the detour candidates that would actually resolve the standoff --
            # a permanent 2-agent deadlock, found by actually running this on
            # the same swap-with-room-to-pass case grid_cbs solves easily (see
            # tests/test_pibt.py), not by reasoning about it in the abstract.
            candidates = sorted(moves, key=lambda c: _manhattan(c, g)) + [here]

            for c in candidates:
                if c in reserved_cells and reserved_cells[c] != agent_id:
                    continue  # already claimed by a decided agent this timestep
                occupant = occupied_by.get(c)
                if occupant is not None and occupant != agent_id:
                    if occupant in frozen_at_goal:
                        continue  # a goal-frozen agent's cell is a hard obstacle
                    if occupant not in decided:
                        moved = decide(occupant)
                        if not moved:
                            continue  # occupant couldn't be pushed out, try next candidate
                    if decided.get(occupant) == c:
                        continue  # occupant decided to stay right where we wanted to go
                decided[agent_id] = c
                reserved_cells[c] = agent_id
                in_progress.discard(agent_id)
                return True

            # No candidate worked: stay put (best effort). This can still
            # collide with the *plan* if another not-yet-processed agent later
            # also claims `here` -- reserved_cells guards exactly that case for
            # already-decided agents, so recording the reservation now is what
            # keeps this sound rather than merely best-effort.
            decided[agent_id] = here
            reserved_cells.setdefault(here, agent_id)
            in_progress.discard(agent_id)
            return False

        for agent_id in sorted(ids, key=lambda a: -priority_value[a]):
            if agent_id not in decided:
                decide(agent_id)

        for agent_id in ids:
            pos[agent_id] = decided[agent_id]
            paths[agent_id].append(decided[agent_id])

        if dynamic_priority:
            # The mechanism that actually gives PIBT its starvation-freedom
            # guarantee: an agent that hasn't reached its goal has its
            # priority grow by 1 every timestep, so an agent repeatedly
            # losing contested cells eventually outranks whatever keeps
            # blocking it. An agent that HAS reached its goal has its
            # priority reset to a low value (here: 0, since this project's
            # one-shot agents freeze at goal and never move again, unlike
            # the lifelong setting the reference scheme was designed for,
            # where a reset-not-frozen agent might be given a new goal
            # later and needs a fair, low starting priority again).
            for aid in ids:
                if pos[aid] == goal[aid]:
                    priority_value[aid] = 0.0
                else:
                    priority_value[aid] += 1.0

    return PIBTResult(
        success=False, paths=paths, runtime_s=time.perf_counter() - t0, timesteps_used=max_timesteps,
    )
