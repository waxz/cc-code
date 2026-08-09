# MovingAI Benchmark Data — Provenance and Attribution

`random-32-32-20.map` and `random-32-32-20-random-1.scen` are from Nathan
Sturtevant's MovingAI 2D Pathfinding Benchmarks, the standard benchmark dataset
used across the single-agent and multi-agent pathfinding literature (this project's
own `docs/related_work.md` already cites several papers that use it, including the
Paris/Berlin maps referenced in the MAPF survey).

**Citation** (please cite if you use this data):

> Sturtevant, N. (2012). Benchmarks for Grid-Based Pathfinding. *IEEE Transactions
> on Computational Intelligence and AI in Games*, 4(2), 144–148.
> DOI: 10.1109/TCIAIG.2012.2197681

**Source**: obtained from the `random-32-32-20.map` / `random-32-32-20-random-1.scen`
files committed directly in `Jiaoyang-Li/MAPF-LNS2` (branch `init-LNS`), a common
practice in this literature since these files are small and widely redistributed
for research use — see `docs/related_work.md` for that project's own citation.
Primary distribution: https://movingai.com/benchmarks/mapf/index.html

**Format**: `.map` is Sturtevant's octile grid format (`.` = passable, `@`/`T`/`O` =
blocked); `.scen` version 1 gives (start, goal, known-optimal-path-length) tuples,
where the optimal length assumes octile distance (diagonal moves cost √2) and that
agents cannot cut corners through walls (a diagonal move is only legal if both
orthogonal cells adjacent to it are also passable). `src/single_agent/movingai_io.py`
implements both rules; `src/single_agent/benchmark.py` checks solved-path costs
against the scen file's known-optimal column as the success criterion.

**Scope**: only `random-32-32-20` is included here (100 scenarios), not the full
benchmark suite (24 maps across game/street/maze/random/room categories) — this is
enough to validate and benchmark the single-agent search this project's low-level
planners depend on without committing a large binary data pull; extending to more
maps is a matter of adding more files to this directory, not a code change.
