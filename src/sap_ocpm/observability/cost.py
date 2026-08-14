"""Cost accounting across one or more RunTraces.

Per-run cost comes straight from the SDK (see trace.py's design note);
this module just aggregates it across a full pipeline invocation
(planner + critic, or a batch of eval-harness runs) so "what does this
cost to operate" has a one-line answer instead of requiring someone to
sum JSON files by hand.
"""
from __future__ import annotations

from dataclasses import dataclass

from sap_ocpm.observability.trace import RunTrace


@dataclass
class CostSummary:
    n_runs: int
    total_cost_usd: float
    by_agent: dict[str, float]
    unknown_cost_runs: int  # runs where the SDK didn't report a cost (e.g. errored before completion)


def summarize_cost(traces: list[RunTrace]) -> CostSummary:
    by_agent: dict[str, float] = {}
    total = 0.0
    unknown = 0
    for t in traces:
        if t.total_cost_usd is None:
            unknown += 1
            continue
        total += t.total_cost_usd
        by_agent[t.agent] = by_agent.get(t.agent, 0.0) + t.total_cost_usd
    return CostSummary(
        n_runs=len(traces),
        total_cost_usd=round(total, 6),
        by_agent={k: round(v, 6) for k, v in by_agent.items()},
        unknown_cost_runs=unknown,
    )
