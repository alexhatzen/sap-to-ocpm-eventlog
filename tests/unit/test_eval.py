"""Unit tests for the eval harness — metrics computation and the
cassette-mode runner, all offline (no live planner calls; the one real
cassette here was seeded from an actual live run, see BACKLOG.md).
"""
from __future__ import annotations

import asyncio

from eval.metrics import compute_metrics
from eval.run_eval import load_cases, run
from eval.schema import EvalCase
from sap_ocpm.agents.schemas import ActivityMapping, ProcessPlan


def _plan(tables_referenced, activities=None) -> ProcessPlan:
    return ProcessPlan(
        process_name="p", process_description="d", document_flow=[],
        activities=activities or [],
        case_granularity="item", case_granularity_rationale="r",
        tables_referenced=tables_referenced,
    )


def test_compute_metrics_perfect_match():
    plan = _plan(["EKKO", "EKPO"])
    m = compute_metrics("case1", ["EKKO", "EKPO"], plan)
    assert m.table_recall == 1.0
    assert m.table_precision == 1.0
    assert m.hallucinated_table_rate == 0.0
    assert m.missing_tables == []
    assert m.extra_tables == []


def test_compute_metrics_partial_recall_and_extra_tables():
    plan = _plan(["EKKO", "EKPO", "LFA1"])
    m = compute_metrics("case2", ["EKKO", "EKPO", "EKBE"], plan)
    assert m.table_recall == round(2 / 3, 3)
    assert m.table_precision == round(2 / 3, 3)
    assert m.missing_tables == ["EKBE"]
    assert m.extra_tables == ["LFA1"]


def test_compute_metrics_catches_hallucinated_table():
    plan = _plan(["EKKO", "EKKO_ITEM"])  # the canary
    m = compute_metrics("case3", ["EKKO"], plan)
    assert m.hallucinated_tables == ["EKKO_ITEM"]
    assert m.hallucinated_table_rate == 0.5


def test_compute_metrics_join_validity_for_real_and_fake_join():
    plan = _plan(
        ["EKPO", "EKBE", "CDHDR"],
        activities=[
            ActivityMapping(activity_name="a", source_tables=["EKPO", "EKBE"]),  # real join
            ActivityMapping(activity_name="b", source_tables=["EKBE", "CDHDR"]),  # no declared path
        ],
    )
    m = compute_metrics("case4", ["EKPO", "EKBE", "CDHDR"], plan)
    assert ("EKBE", "CDHDR") in m.invalid_join_pairs
    assert m.join_validity_rate == 0.5  # 1 of 2 checked pairs valid


def test_load_cases_returns_valid_eval_cases():
    cases = load_cases()
    assert len(cases) >= 2
    assert all(isinstance(c, EvalCase) for c in cases)
    assert all(c.expected_tables for c in cases)


def test_run_cassette_mode_uses_seeded_cassette():
    results, skipped = asyncio.run(run(include_drafts=True, live=False))
    result_ids = {r.case_id for r in results}
    assert "3way_match_item_level" in result_ids
    # the other draft case has no cassette yet -- must be skipped, not faked
    assert "vendor_payment_timing" in skipped


def test_run_excludes_drafts_by_default():
    results, skipped = asyncio.run(run(include_drafts=False, live=False))
    assert results == []  # both current cases are drafts
