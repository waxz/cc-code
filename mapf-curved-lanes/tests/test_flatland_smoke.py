"""Proves flatland-rl actually runs headless in this project's CI, not just that it
was chosen on paper. See docs/improvement_plan.md section 2 for why it was picked
over Gazebo/Isaac Sim/Webots once the requirement changed to "no physics engine,
must run in GitHub Actions": flatland-rl is pip-installable, has no GPU/display/ROS
dependency, and is real industrial software (built and maintained by SBB, Deutsche
Bahn, and SNCF for railway vehicle rescheduling) that is itself already run inside
automated CI/evaluation pipelines (the AIcrowd Flatland Challenge's evaluator).

This is a smoke test, not yet an integration of our lane-graph solver with
Flatland's environment -- that translation (our continuous curved-lane graph ->
Flatland's grid+rail-topology abstraction) is the next step, analogous to how
src/baselines/grid_cbs.py's instance_to_grid() already translates our instances for
the classical grid-CBS baseline, and would carry a similar, honestly-documented
loss of fidelity (grid+switches, not continuous Frenet-frame curvature).
"""
import time

import numpy as np


def test_flatland_installs_and_runs_headless():
    from flatland.envs.line_generators import sparse_line_generator
    from flatland.envs.rail_env import RailEnv
    from flatland.envs.rail_generators import sparse_rail_generator

    t0 = time.perf_counter()
    env = RailEnv(
        width=30,
        height=30,
        number_of_agents=5,
        rail_generator=sparse_rail_generator(max_num_cities=3),
        line_generator=sparse_line_generator(),
        random_seed=42,
    )
    obs, info = env.reset(random_seed=42)
    assert len(env.agents) == 5

    rng = np.random.default_rng(42)
    for _ in range(20):
        actions = {i: int(rng.integers(0, 5)) for i in range(len(env.agents))}
        obs, rewards, done, info = env.step(actions)
        assert len(rewards) == 5

    elapsed = time.perf_counter() - t0
    # Generous bound for a CI runner -- this ran in ~0.2-0.5s locally with no
    # display and no physics engine, which is the entire point of this test.
    assert elapsed < 10.0
