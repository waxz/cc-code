"""Shrink a failing instance found by src/proving/differential.py down to a
minimal reproducing counterexample, delta-debugging style (Zeller & Hildebrandt,
2002): repeatedly try simpler variants of a failing instance, keep the failure if
a variant still reproduces it, stop when no available simplification still fails.

Why this matters here, concretely: the JPS corner-cutting bug in this project's
history was originally found on a random 6x6 grid with a specific obstacle
pattern -- useful for confirming *that* a bug existed, but not by itself the
clearest evidence of *why*. Manually reducing it to the actual minimal case (three
cells: a straight run interrupted by a single corner-blocking wall) is what made
the root cause legible enough to fix correctly. This module automates that manual
reduction step, which is the part of "automated MAPF proving" that's actually
missing from routine practice in this field (see
docs/research_proposal_proving.md) -- generating a failing random instance is
already common (most projects' test suites have *some* fuzzing); automatically
reducing it to a minimal, human-diagnosable counterexample is not.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, List, Optional

# Given an instance, return zero or more strictly "simpler" candidate instances
# to try next (e.g., a smaller grid, fewer obstacles, a shorter path). The
# shrinker doesn't need to know what "simpler" means for a given domain --
# that's supplied per-instance-type, matching the same separation of concerns
# property-based testing libraries (e.g. Hypothesis) use between generation and
# shrinking strategies.
SimplifyFn = Callable[[Any], List[Any]]
# Returns a discrepancy detail string if the instance still fails, else None --
# same shape as differential.Comparator, so a shrinker can reuse the exact
# comparator that found the original failure.
StillFailsFn = Callable[[Any], Optional[str]]


@dataclass
class ShrinkResult:
    original_instance: Any
    minimal_instance: Any
    minimal_detail: str
    steps_tried: int
    steps_accepted: int


def shrink(
    instance: Any,
    still_fails: StillFailsFn,
    simplify: SimplifyFn,
    original_detail: str,
    max_steps: int = 2000,
) -> ShrinkResult:
    """Greedily shrink `instance`: at each round, try every candidate simplify()
    offers, accept the first one that still fails (and restart rounds from
    there), stop when a full round offers nothing that still fails or max_steps
    is exhausted. This is intentionally simple (not the fastest possible
    delta-debugging variant) so its behavior is easy to verify is correct --
    a shrinker that itself has to be trusted defeats the purpose.
    """
    current = instance
    current_detail = original_detail
    steps_tried = 0
    steps_accepted = 0

    while steps_tried < max_steps:
        candidates = simplify(current)
        if not candidates:
            break
        progressed = False
        for candidate in candidates:
            steps_tried += 1
            if steps_tried >= max_steps:
                break
            detail = still_fails(candidate)
            if detail is not None:
                current = candidate
                current_detail = detail
                steps_accepted += 1
                progressed = True
                break  # restart the simplify() loop from the new, smaller instance
        if not progressed:
            break

    return ShrinkResult(
        original_instance=instance, minimal_instance=current, minimal_detail=current_detail,
        steps_tried=steps_tried, steps_accepted=steps_accepted,
    )
