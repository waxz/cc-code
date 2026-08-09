# Related Work

Annotated bibliography. Where a paper does not have a stable DOI, the arXiv abstract page is
linked (not the raw PDF) so licensing terms remain visible. This project does not vendor any
paper PDFs — clone/read them from these links directly.

## Continuous-space / non-holonomic MAPF (closest baselines)

- **Wen, Liu, Li. "CL-MAPF: Multi-Agent Path Finding for Car-Like Robots with Kinematic and
  Spatiotemporal Constraints."** Robotics and Autonomous Systems, 2022.
  arXiv: https://arxiv.org/abs/2011.00441
  Introduces CL-MAPF and the CL-CBS solver: Reeds–Shepp low-level planner, body-conflict tree
  for collision checking on curved swept volumes. Primary baseline #2 in this project. Also the
  source of the benchmark-generation methodology this project's instance generator follows
  (multiple map sizes, obstacle/no-obstacle scenarios, 60 instances per configuration).

- **"Multi-agent Path Planning Based on Conflict-Based Search (CBS) Variations for
  Heterogeneous Robots" (HCBS/EHCBS/DFHCBS).** Journal of Intelligent & Robotic Systems, 2025.
  https://link.springer.com/article/10.1007/s10846-025-02229-0
  Mixes holonomic and non-holonomic agents in one conflict tree via a body-conflict detection
  strategy; hybrid A* for car-like agents, plain A* for holonomic agents. Primary baseline #3.
  Fixed kinematics per agent class — this project's load-dependent extension targets exactly
  this limitation.

- **"Multi-Agent Path Finding Using Conflict-Based Search and Structural-Semantic Topometric
  Maps."** arXiv:2501.17661, 2025. https://arxiv.org/abs/2501.17661
  Real-world non-holonomic robot validation; corridor-symmetry handling improvements relevant
  to the lane-graph junction-conflict design.

- **"Clique Analysis and Bypassing in Continuous-Time Conflict-Based Search."**
  arXiv:2312.16106. https://arxiv.org/abs/2312.16106
  Continuous-time CBS variants; relevant to the swept-volume junction-conflict checker.

## Surveys (background / positioning)

- **Wang, Xu, Zhang, Lin, Lu, Wang, Li. "Where Paths Collide: A Comprehensive Survey of
  Classic and Learning-Based Multi-Agent Pathfinding."** arXiv:2505.19219 (preprint, under
  review). https://arxiv.org/abs/2505.19219
  Unified taxonomy of search-based, compilation-based, and learning-based MAPF; identifies the
  classical-vs-learning evaluation-scale mismatch (1000+ agents vs. 10-100 agents) and lists
  open directions including generative and language-grounded MAPF. Used here mainly for
  positioning and for the CBS/PBS/LNS pseudocode this project's high-level search follows.

## Search-based classical MAPF (algorithmic building blocks)

- **Sharon, Stern, Felner, Sturtevant. "Conflict-Based Search for Optimal Multi-Agent
  Pathfinding."** Artificial Intelligence, 2015. Foundational CBS paper; this project's
  high-level search is a direct generalization of its conflict-tree branching rule.

- **Okumura. "LaCAM: Lazy Constraints Addition Search."** And **LaCAM\*** (eventually-optimal
  variant). Relevant if/when this project needs to scale beyond conflict-tree branching for
  large fleets.

- **Li, Chen, Harabor, Stuckey, Koenig. "MAPF-LNS2: Fast Repairing for Multi-Agent Path
  Finding via Large Neighborhood Search."** AAAI 2022. Destroy-repair meta-heuristic; candidate
  approach for scaling this project's solver past conflict-tree branching limits.

## Execution / kinodynamic refinement

- **Yan, Smith, Li. "WinkTPG: An Execution Framework for Multi-Agent Path Finding Using
  Temporal Reasoning."** arXiv:2508.01495. https://arxiv.org/abs/2508.01495
  Refines a MAPF plan into kinodynamically feasible speed profiles post-hoc. Motivates this
  project's plan-then-refine separation between the MAPF coordination layer and full-body
  legged execution.

## Mixed traffic / lane-graph representations

- **Zheng, Yan, Wu. "Multi-agent Path Finding for Mixed Autonomy Traffic Coordination."**
  arXiv:2409.03881. https://arxiv.org/abs/2409.03881
  MAPF over road-network-style representations with uncontrollable human-driven vehicles;
  relevant precedent for this project's clothoid lane-graph map representation.

## Benchmarking infrastructure

- **"A Benchmark for Multi-Robot Planning in Realistic, Unstructured Environments" (MRP-Bench).**
  ICRA 2023. https://idm-lab.org/bib/abstracts/papers/icra23.pdf
  RMF traffic editor + Gazebo world generation + ROS2 orchestration for building-scale
  multi-robot benchmarking. Used in `docs/benchmark_plan.md` as the recommended tool for
  physical-plausibility validation rather than building a simulator from scratch.

## Industrial-scale global planning algorithms (see docs/improvement_plan.md)

- **Okumura, Machida, Défago, Tamura. "Priority Inheritance with Backtracking for
  Iterative Multi-Agent Path Finding."** Artificial Intelligence, 2022 (IJCAI 2019
  original). https://www.ijcai.org/proceedings/2019/0076.pdf
  PIBT: one-timestep, priority-based replanning with backtracking to break
  deadlocks. Directly addresses this project's documented wait-only-incompleteness
  limitation (see docs/benchmark_plan.md) by rerouting every timestep instead of
  fixing a route once. Reported capable of hundreds of agents in under 200ms.

- **Jiang, Wang, Veerapaneni, Duhan, Sartoretti, Li. "Deploying Ten Thousand
  Robots: Scalable Imitation Learning for Lifelong Multi-Agent Path Finding."**
  ICRA 2025. https://arxiv.org/abs/2410.21415
  Context on WPPL (PIBT + windowed MAPF-LNS), winner of the 2023 Amazon-sponsored
  League of Robot Runners competition; validated on 10 real + 100 virtual robots.

- **Okumura. "db-LaCAM: Fast and Scalable Multi-Robot Kinodynamic Motion Planning
  with Discontinuity-Bounded Search and Lightweight MAPF."**
  https://arxiv.org/abs/2512.06796
  Combines lightweight MAPF with discontinuity-bounded search for real vehicle
  kinematics rather than point-mass agents on a graph -- sits close to this
  project's own heterogeneous/kinodynamic/non-grid niche; flagged in
  docs/improvement_plan.md as worth reading closely before choosing how to replace
  the current Dijkstra-based low-level planner.

- **Li, Tinka, Kiesel, Durham, Kumar, Koenig. "Lifelong Multi-Agent Path Finding in
  Large-Scale Warehouses."** AAAI 2021 (AAMAS 2020 original).
  The Amazon Robotics collaboration paper this project's "cycle time" and
  "throughput" metrics (docs/improvement_plan.md section 3) are drawn from.

## Collision avoidance (see docs/improvement_plan.md)

- **van den Berg, Guy, Lin, Manocha. "Reciprocal n-Body Collision Avoidance."**
  ISRR 2011 (the original ORCA paper).
  Recommended as the local reactive safety layer beneath the global planner --
  mature, well-understood, the most widely used reciprocal collision-avoidance
  algorithm in both multi-robot systems and crowd simulation.

- **"Forecast-Driven MPC for Decentralized Multi-Robot Collision Avoidance."**
  2025. https://arxiv.org/abs/2508.08264
  And **"CoRL-MPPI: Enhancing MPPI With Learnable Behaviours For Efficient And
  Provably-Safe Multi-Robot Collision Avoidance."** 2026.
  https://arxiv.org/abs/2511.09331
  MPC/MPPI-based local layers, reporting better collision-free success rates than
  reactive one-step methods in dense/high-speed scenarios at the cost of heavier
  per-step computation. Flagged as the phase-2 stretch option in
  docs/improvement_plan.md, contingent on ORCA's known failure modes actually
  binding in this project's curved-lane setting.

## Notes on citation hygiene

This bibliography lists titles, authors, venues, and links only — no reproduced abstracts or
quoted text beyond what is needed to describe relevance. Pull full text from the linked
sources directly rather than from any copy in this repository.
