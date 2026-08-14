"""Eval harness runner.

Cassette mode (default): loads a cached planner-output JSON per case
from cassettes/<case_id>.json — no ANTHROPIC_API_KEY / claude CLI
needed, deterministic, safe for CI. Cases with no cassette are
reported as skipped, never silently dropped or faked.

Live mode (--live): actually runs the planner for each case and
(over)writes its cassette — costs tokens, needs the same live setup
the agents module needs.

Usage:
  PYTHONPATH=src:. python3 eval/run_eval.py
  PYTHONPATH=src:. python3 eval/run_eval.py --include-drafts
  PYTHONPATH=src:. python3 eval/run_eval.py --live
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import yaml

from eval.metrics import EvalMetrics, aggregate, compute_metrics
from eval.schema import EvalCase
from sap_ocpm.agents.schemas import ProcessPlan

CASES_DIR = Path(__file__).parent / "cases"
CASSETTES_DIR = Path(__file__).parent / "cassettes"


def load_cases() -> list[EvalCase]:
    cases = []
    for path in sorted(CASES_DIR.glob("*.yaml")):
        cases.append(EvalCase.model_validate(yaml.safe_load(path.read_text())))
    return cases


def _cassette_path(case_id: str) -> Path:
    return CASSETTES_DIR / f"{case_id}.json"


async def _get_plan(case: EvalCase, live: bool) -> ProcessPlan | None:
    cassette = _cassette_path(case.id)
    if live:
        from sap_ocpm.agents.planner import run_planner

        plan, _trace = await run_planner(case.use_case)
        cassette.write_text(json.dumps(plan.model_dump(), indent=2))
        return plan
    if cassette.exists():
        return ProcessPlan.model_validate(json.loads(cassette.read_text()))
    return None


async def run(*, include_drafts: bool, live: bool) -> tuple[list[EvalMetrics], list[str]]:
    cases = load_cases()
    if not include_drafts:
        cases = [c for c in cases if not c.is_draft]

    results: list[EvalMetrics] = []
    skipped: list[str] = []
    for case in cases:
        plan = await _get_plan(case, live)
        if plan is None:
            skipped.append(case.id)
            continue
        results.append(compute_metrics(case.id, case.expected_tables, plan))

    return results, skipped


def render_results_table(results: list[EvalMetrics], skipped: list[str], drafts_included: bool) -> str:
    lines = [
        "# Eval results",
        "",
        f"Draft cases included: {drafts_included}. "
        f"{'⚠️ Numbers below include unreviewed draft cases — treat as a harness smoke test, not a validated benchmark.' if drafts_included else ''}",
        "",
        "| case | table recall | table precision | hallucinated table rate | join validity rate |",
        "|---|---|---|---|---|",
    ]
    for m in results:
        jv = f"{m.join_validity_rate:.3f}" if m.join_validity_rate is not None else "n/a"
        lines.append(f"| {m.case_id} | {m.table_recall:.3f} | {m.table_precision:.3f} | {m.hallucinated_table_rate:.3f} | {jv} |")

    if results:
        agg = aggregate(results)
        lines += [
            "",
            f"**Aggregate over {agg.n_cases} case(s):** table recall {agg.mean_table_recall:.3f}, "
            f"table precision {agg.mean_table_precision:.3f}, "
            f"**hallucinated table rate {agg.hallucinated_table_rate:.3f}** "
            f"{'(must be 0 — ' + ('OK' if agg.hallucinated_table_rate == 0 else 'FAIL') + ')'}, "
            f"join validity rate {f'{agg.mean_join_validity_rate:.3f}' if agg.mean_join_validity_rate is not None else 'n/a'}.",
        ]
    else:
        lines.append("\n(no cases with results — nothing to aggregate)")

    if skipped:
        lines += ["", f"Skipped (no cassette, not run live): {', '.join(skipped)}"]

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--include-drafts", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--fail-on-hallucination", action="store_true", default=True)
    args = parser.parse_args()

    results, skipped = asyncio.run(run(include_drafts=args.include_drafts, live=args.live))
    table = render_results_table(results, skipped, args.include_drafts)
    print(table)

    out_path = Path(__file__).parent / "RESULTS.md"
    out_path.write_text(table + "\n")

    if results and args.fail_on_hallucination:
        agg = aggregate(results)
        if agg.hallucinated_table_rate != 0:
            print("\nFAIL: hallucinated_table_rate must be 0", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
