from src.baselines.pibt import PIBTAgent, solve_pibt


def _check_collision_free(paths):
    ids = list(paths.keys())
    maxlen = max(len(p) for p in paths.values())
    padded = {i: paths[i] + [paths[i][-1]] * (maxlen - len(paths[i])) for i in ids}
    for t in range(maxlen):
        seen = {}
        for i in ids:
            c = padded[i][t]
            if c in seen:
                return False
            seen[c] = i
    for t in range(maxlen - 1):
        for i in ids:
            for j in ids:
                if i >= j:
                    continue
                if padded[i][t] == padded[j][t + 1] and padded[i][t + 1] == padded[j][t]:
                    return False
    return True


def test_pibt_resolves_swap_with_room_to_pass():
    agents = [PIBTAgent("a0", (0, 1), (2, 1)), PIBTAgent("a1", (2, 1), (0, 1))]
    result = solve_pibt(agents, width=3, height=3)
    assert result.success
    assert _check_collision_free(result.paths)


def test_pibt_does_not_deadlock_on_head_on_corridor_with_no_detour():
    """Regression test for the candidate-ordering bug: an earlier version
    ranked 'stay' among genuine moves by raw distance-to-goal, so two agents
    approaching head-on both found staying locally better than a detour and
    neither ever tried one -- a permanent deadlock on exactly the swap case
    above before the fix (see src/baselines/pibt.py's _jump-adjacent comment
    in `decide()`). This grid has NO detour available at all (single-width
    corridor), so the correct behavior is to correctly report failure, not
    hang or crash -- verifying the fix didn't just relocate the bug.
    """
    agents = [PIBTAgent("a0", (0, 0), (2, 0)), PIBTAgent("a1", (2, 0), (0, 0))]
    result = solve_pibt(agents, width=3, height=1, max_timesteps=50)
    assert not result.success  # genuinely unsolvable -- no room to pass


def test_pibt_freezes_agents_at_goal_instead_of_oscillating():
    """Regression test for the goal-oscillation bug: a specific 5-agent, 10x7
    open-grid instance (no obstacles at all) that previously failed because
    agents at their own goal kept getting displaced and immediately trying to
    return, oscillating forever instead of succeeding. Locked in with the
    exact instance that found the bug, not a paraphrase of it.
    """
    agents = [
        PIBTAgent("a0", (8, 4), (6, 1)), PIBTAgent("a1", (3, 3), (9, 4)),
        PIBTAgent("a2", (9, 6), (3, 5)), PIBTAgent("a3", (7, 0), (7, 6)),
        PIBTAgent("a4", (7, 5), (2, 0)),
    ]
    result = solve_pibt(agents, width=10, height=7, max_timesteps=200, priority_seed=0)
    assert result.success
    assert _check_collision_free(result.paths)


def test_pibt_collision_free_across_many_random_instances():
    import random

    rng = random.Random(0)
    n_trials = 150
    n_successes = 0
    for trial in range(n_trials):
        w, h = rng.randint(4, 10), rng.randint(4, 10)
        n_agents = rng.randint(2, 5)
        all_cells = [(x, y) for x in range(w) for y in range(h)]
        rng.shuffle(all_cells)
        chosen = all_cells[: 2 * n_agents]
        starts, goals = chosen[:n_agents], chosen[n_agents:]
        agents = [PIBTAgent(f"a{i}", starts[i], goals[i]) for i in range(n_agents)]
        result = solve_pibt(agents, width=w, height=h, max_timesteps=200, priority_seed=trial)
        if result.success:
            n_successes += 1
            assert _check_collision_free(result.paths), f"collision at trial {trial}"
    # Measured at 84.0% on a larger (500-trial) run -- a looser bound here
    # avoids CI flakiness from trial-count variance while still catching a
    # regression that tanks the success rate.
    assert n_successes / n_trials > 0.6
