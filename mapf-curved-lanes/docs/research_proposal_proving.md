# Research Proposal: Differential Testing and Automated Counterexample
# Generation for MAPF and Pathfinding Implementations

Status: proof-of-concept implemented and run (`src/proving/`); this document
reports what was actually measured, not a projection of what the approach
should do in principle.

## 1. The gap, and why it's a gap rather than solved-elsewhere

"Where Paths Collide: A Comprehensive Survey of Classic and Learning-Based
Multi-Agent Pathfinding" (Wang, Xu, Zhang, Lin, Lu, Wang, Li; arXiv:2505.19219)
identifies **Automated MAPF Proving** (Section 9.7) as a future direction: coupling
automated theorem proving frameworks (specifically Lean4) with MAPF solvers to
"verify key properties of conflict resolution, priority assignments, or
subproblem-specific constraints, thus yielding robust correctness certificates
and facilitating the discovery of overlooked corner cases." The same section
explicitly names the byproduct this proposal targets: coupling verification with
methods that can "produce counterexamples when violations occur."

Full formal verification (encoding CBS/PBS/JPS in Lean4 and proving their
correctness properties as theorems) is the survey's stated long-term direction,
and it is a substantial undertaking — it requires a machine-checkable formal
model of the algorithm, the target language's proof ecosystem, and specialist
expertise most MAPF researchers and engineers don't have. That's a real barrier,
and it's why this gap remains open despite the field publishing 200+ MAPF papers
in the survey's own review.

**This proposal targets a narrower, lower-barrier piece of the same gap**:
automated counterexample generation via differential testing, without full formal
proof. This is not a competing idea to the survey's Lean4 direction — it is a
practical predecessor to it, in the same relationship compiler fuzzing (Csmith;
Yang, Chen, Eide, Regehr, "Finding and Understanding Bugs in C Compilers", PLDI
2011) has to formally verified compilers (CompCert; Leroy, 2009): fuzzing found
hundreds of real miscompilation bugs in production C compilers years before and
independently of any full formal-verification effort, and the counterexamples it
generated are exactly the kind of concrete, minimal evidence a subsequent formal
verification effort needs to know what to prove. No equivalent tool exists for
MAPF/pathfinding solver *implementations* (as opposed to algorithm-level proofs on
paper) — that absence is the actual, specific gap this proposal addresses.

## 2. Evidence the gap is real, not assumed

This project's own development history supplies two independent, previously
undiscovered-by-inspection bugs, both found only by exactly this kind of testing:

1. **`src/single_agent/grid_planners.py::jps`** — a first implementation targeted
   the wrong cost model (corner-cutting disallowed, matching this project's other
   planners) and failed on 388 of 409 real MovingAI benchmark scenarios. It passed
   every hand-picked test case checked before the fuzz test was run. The root
   cause was a genuine algorithmic subtlety (classical JPS's pruning proof
   implicitly assumes a diagonal shortcut is always geometrically available,
   which is false once corners can be blocked) — not a typo, and not something
   code review would reliably catch, since the code *looked* like a correct
   translation of the published algorithm.
2. **`src/high_level/conflict_tree.py`** (this project's CBS/PBS high-level
   search) — an early version generated constraints that blocked a zero-width
   time instant instead of the true conflict-overlap window, causing the search
   to loop indefinitely without progress on multi-agent instances, discovered
   only by tracing an actual non-converging run, not by reading the branching
   logic.

Both bugs are documented in this repository's own commit history precisely
because they were found this way. Neither would have been caught by the kind of
evaluation the survey itself flags as standard practice in the field (Section 8):
success-rate reporting on a fixed, often small or curated, benchmark set.

## 3. Proposed method

Three components, all implemented in `src/proving/`:

### 3.1 Differential testing engine (`differential.py`)

Generates `n_trials` random problem instances via a supplied generator, runs a
supplied `Comparator` on each, and collects every discrepancy (bounded, so a
badly broken candidate doesn't produce an unusable report). Each trial's random
seed is derived deterministically from the run seed and trial index, so any
failure is independently reproducible from the seed alone — required for the
shrinking step to re-run isolated trials.

The `Comparator` abstraction is deliberately general enough to express three
different kinds of correctness claim with the same engine, all three of which
this proposal's proof-of-concept actually exercises (not just claims to support
in principle):

- **Cross-implementation agreement under a shared cost model**
  (`dijkstra` vs. `astar` — both must find the exact same optimal cost).
- **Cross-implementation agreement under a *matching but distinct* cost model**
  (`jps` vs. `dijkstra_allow_corner_cutting` — a different model from the
  project's main planners, so it must be compared against the matching
  reference, not the main one).
- **Self-consistency against a single implementation's own claimed invariants**
  (the multi-agent solver's returned solution must actually be conflict-free and
  its reported cost must match the recomputed cost from its own trajectories —
  there is no second implementation at this fidelity to compare against, so the
  check is against the solver's own claims about its own output).

### 3.2 Delta-debugging shrinker (`shrink.py`)

Given a failing instance and a domain-specific `simplify()` function that
proposes strictly smaller candidate instances, greedily accepts any candidate
that still reproduces the failure and repeats from there, stopping when no
further simplification still fails (Zeller & Hildebrandt's delta-debugging,
2002). Deliberately the simplest correct version of this algorithm (not the
fastest), so its own behavior doesn't need to be trusted blindly — a shrinker
subtle enough to need its own bug hunt would defeat the purpose.

### 3.3 Domain-specific generators and simplifiers (`grid_instances.py`,
`mapf_instances.py`, `comparators.py`)

Random grid instances (variable size, variable obstacle density — chosen because
this project's real JPS bug was density-sensitive, so a fixed density could have
hidden it) with two simplification strategies (crop an edge, unblock one
obstacle), and random small MAPF instances reusing this project's own
`generate_instances.py` rather than duplicating instance-generation logic.

## 4. Proof-of-concept results (measured, this run)

### 4.1 Validating the tool itself, on a bug with known ground truth

Before trusting the framework on anything real, it needed to demonstrably catch
a bug where the answer was already known. The first attempt at a seeded bug — an
inadmissible A* heuristic (a deliberately overestimating octile heuristic) —
produced **0/500 failures**, including with the overestimate increased 10x. This
negative result was itself informative once understood rather than discarded: a
*uniform* additive constant added to every node's heuristic provably cannot
change A*'s relative expansion order (the constant cancels in every pairwise
comparison), and the direction-dependent variant tried apparently stayed too
small relative to typical cost gaps on these grid sizes to ever flip the final
answer. This is documented in `src/proving/seeded_bug_demo.py` rather than
silently replaced with a working example as if the first attempt had never
happened.

The bug actually used is blunter: a Dijkstra copy that omits the four diagonal
moves (`buggy_dijkstra_missing_diagonals`) — a realistic, easy-to-make
implementation slip. Measured:

```
500 trials, 289 failures (57.80%)
```

Shrinking one failure (originally a 10×10 grid with several obstacles) produced:

```
MINIMAL instance (2 x 2):
S.
.G
detail: cost mismatch: reference=1.414214 candidate=2.000000
shrink steps tried=20 accepted=16
```

— a start/goal pair on opposite corners of a 2×2 grid, where the real planner
takes one diagonal step (cost √2) and the buggy one is forced around two
orthogonal moves (cost 2). This is the bug stated in its clearest possible form,
produced automatically from a 100-cell random instance with no obstacle
relevant to the actual defect. The first version of the shrinker's crop strategy
had a real bug of its own, caught the same way this whole approach catches
bugs generally: it guarded against cropping any edge touching start or goal,
which is *always* true for the corner-to-corner start/goal convention used
here, so it silently never fired — found by inspecting an actual shrink run
that stalled at the original grid size instead of reducing it, fixed by moving
start/goal inward with the crop instead of skipping it.

### 4.2 Applying it for real to this project's production single-agent code

```
dijkstra vs. astar:                              8000 trials, 0 failures
jps vs. dijkstra_allow_corner_cutting:            8000 trials, 0 failures
```

This reinforces (at 8000 trials rather than the original 20,000-trial and
409-scenario checks reported in `docs/single_agent_benchmark.md`) that both
production planners remain correct — a genuine additional data point, not a
redundant one, since this run uses an independently-written generator and
engine rather than the original ad hoc fuzz scripts.

### 4.3 Applying it for real to code that had never been tested this way before

The multi-agent solver's self-consistency (soundness) property — a returned
"success" must actually be conflict-free and cost-consistent — had never been
checked by randomized testing before this proposal, only by hand-traced examples
during earlier debugging. Result:

```
mode=cbs: 500 trials, 0 failures
mode=pbs: 500 trials, 0 failures
```

**Reported honestly, including what this does and doesn't mean**: zero failures
across 1000 random trials is a genuine positive result — when this solver
reports success, that claim appears trustworthy across a wide range of random
small instances, in both search modes. It is **not** evidence against the
already-documented completeness gap (`docs/benchmark_plan.md`: the solver can
fail to find a solution that exists, because its low-level planner can wait but
not reroute around a contested segment). This check only examines instances
where the solver *reports* success; it says nothing about instances where it
reports failure but a solution existed. Soundness and completeness are different
properties, and this proof-of-concept validates the former, not the latter — a
distinction worth stating precisely rather than letting a clean 0-failures
result imply more than it does.

## 5. What this proposal does not claim

- Not a replacement for the survey's Lean4/ATP direction — a positive
  differential-testing result is evidence, not a proof; the framework can fail
  to find a bug that exists (as arguably nearly happened with the JPS bug, which
  needed a large trial count and adversarial density variation to manifest
  reliably, and did not manifest at all under the first, more conservative
  fuzzing parameters tried during that debugging).
- Not evidence the multi-agent solver is complete — see §4.3.
- Not validated yet against any pathfinding implementation outside this
  project's own codebase — the natural next step (§6) is running it against a
  public reference implementation (e.g., the PIBT/LaCAM reference code already
  cited in `docs/related_work.md`) to see whether it surfaces anything there,
  which would be much stronger evidence of general usefulness than only
  succeeding on code written with this exact framework in mind.

## 6. Next steps, in priority order

1. Run the framework against a public MAPF reference implementation not written
   by this project (candidates already in `docs/related_work.md`: the PIBT
   reference at `github.com/Kei18/pibt`, or `Jiaoyang-Li/MAPF-LNS2`) — the
   strongest test of whether this generalizes beyond code shaped by having this
   tool in mind from the start.
2. Extend the property catalog beyond the two implemented here (cost agreement,
   solution self-consistency) to completeness-adjacent properties where
   feasible — e.g., for a bounded-size instance, cross-check "solver reports
   infeasible" against an expensive but trusted brute-force search, which is
   tractable only for very small instances but would directly probe the
   soundness/completeness gap flagged in §4.3.
3. If either of the above surfaces a real bug in code this project doesn't
   control, that is the strongest possible validation of the approach's value
   to the wider field, not just to this project — and is the natural bridge
   toward the survey's fuller Lean4-based vision, since a library of
   machine-found, minimal counterexamples is exactly the kind of concrete
   target a subsequent formal-verification effort needs.
