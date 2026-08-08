from src.baselines.grid_cbs import GridAgent, instance_to_grid, solve_grid_cbs
from src.benchmark.generate_instances import AgentSpec
from src.lane_graph.graph import JunctionNode, LaneGraph, LaneSegment


def test_grid_cbs_resolves_swap_with_room_to_pass():
    agents = [GridAgent("a0", (0, 1), (2, 1)), GridAgent("a1", (2, 1), (0, 1))]
    result = solve_grid_cbs(agents, width=3, height=3)
    assert result.success
    assert result.sum_of_costs > 0
    # sanity: no two agents share a cell at any timestep
    max_len = max(len(p) for p in result.paths.values())
    padded = {aid: p + [p[-1]] * (max_len - len(p)) for aid, p in result.paths.items()}
    for t in range(max_len):
        cells = [padded[aid][t] for aid in padded]
        assert len(cells) == len(set(cells))


def test_grid_cbs_infeasible_swap_in_single_width_corridor():
    # No room to pass: classic unsolvable point-agent swap.
    agents = [GridAgent("a0", (0, 0), (2, 0)), GridAgent("a1", (2, 0), (0, 0))]
    result = solve_grid_cbs(agents, width=3, height=1, max_expansions=50)
    assert not result.success


def test_instance_to_grid_snaps_nodes_to_cells():
    g = LaneGraph()
    g.add_node(JunctionNode("a", (0.0, 0.0)))
    g.add_node(JunctionNode("b", (10.0, 0.0)))
    g.add_segment(LaneSegment("s1", "a", "b", length=10.0, width=3.0))
    specs = [AgentSpec("fk_0", "forklift", "a", "b", "empty")]
    agents, width, height = instance_to_grid(g, specs, cell_size=5.0)
    assert width >= 2
    assert agents[0].start != agents[0].goal
