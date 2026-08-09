"""Random small MAPF instance generator for
src/proving/comparators.py::mapf_solution_self_consistency_comparator, reusing
src/benchmark/generate_instances.py rather than duplicating instance-generation
logic.
"""
from __future__ import annotations

import random

from src.benchmark.generate_instances import generate_instance

_MAP_SIZES = ["small", "medium"]
_DENSITIES = ["low", "medium", "high"]


def random_mapf_instance(rng: random.Random):
    map_size = rng.choice(_MAP_SIZES)
    density = rng.choice(_DENSITIES)
    n_agents = rng.randint(2, 5)
    forklift_pct = rng.choice([0, 50, 100])
    fleet_mix = f"{forklift_pct}:{100 - forklift_pct}"
    seed = rng.randint(0, 1_000_000)
    return generate_instance(
        instance_id=f"proving_{seed}",
        map_size=map_size,
        junction_density=density,
        n_agents=n_agents,
        fleet_mix=fleet_mix,
        seed=seed,
    )
