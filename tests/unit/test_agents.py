"""Unit tests for the planner/critic agent scaffolding — the
deterministic parts only (JSON extraction, rendering, schema
validation). Live agent runs (which need ANTHROPIC_API_KEY / the
`claude` CLI and cost real tokens) are verified manually, not in this
automated suite — same reasoning as dataprep's live streaming path.
"""
from __future__ import annotations

import pytest

from sap_ocpm.agents.critic import CriticError, _extract_json_block as critic_extract, render_report
from sap_ocpm.agents.planner import PlannerError, _extract_json_block as planner_extract, render_plan
from sap_ocpm.agents.schemas import (
    ActivityMapping,
    ConfidenceNote,
    CriticFinding,
    CriticReport,
    PlanGap,
    ProcessPlan,
)


def _minimal_plan() -> ProcessPlan:
    return ProcessPlan(
        process_name="Test Process",
        process_description="A test process",
        document_flow=["Purchase Order", "Goods Receipt"],
        activities=[ActivityMapping(activity_name="Create PO Item", source_tables=["EKPO"], notes="")],
        case_granularity="item",
        case_granularity_rationale="matches the use case",
        tables_referenced=["EKKO", "EKPO"],
        known_gaps=[PlanGap(category="timestamp", description="EKPO has no creation timestamp")],
        confidence_notes=[ConfidenceNote(topic="joins", confidence="high", rationale="verified via KB")],
    )


# --- JSON extraction (shared logic, tested via both modules' copies) ---

def test_extract_json_block_from_fenced_block():
    text = 'Some reasoning first.\n```json\n{"a": 1}\n```\n'
    assert planner_extract(text) == {"a": 1}
    assert critic_extract(text) == {"a": 1}


def test_extract_json_block_bare_json_fallback():
    assert planner_extract('{"a": 1}') == {"a": 1}


def test_extract_json_block_raises_on_garbage():
    with pytest.raises(PlannerError):
        planner_extract("not json at all")
    with pytest.raises(CriticError):
        critic_extract("not json at all")


# --- ProcessPlan schema -------------------------------------------------

def test_process_plan_rejects_invalid_case_granularity():
    with pytest.raises(Exception):
        ProcessPlan(
            process_name="x", process_description="x", document_flow=[],
            activities=[], case_granularity="header",  # invalid, must be item|order
            case_granularity_rationale="x", tables_referenced=[],
        )


def test_process_plan_round_trips_through_json():
    plan = _minimal_plan()
    restored = ProcessPlan.model_validate_json(plan.model_dump_json())
    assert restored == plan


# --- render_plan / render_report ----------------------------------------

def test_render_plan_includes_key_sections():
    text = render_plan(_minimal_plan())
    assert "Test Process" in text
    assert "Create PO Item" in text
    assert "Known gaps:" in text
    assert "Confidence notes:" in text


def test_render_report_shows_findings_and_approval():
    report = CriticReport(
        approved=False,
        findings=[CriticFinding(severity="error", category="hallucinated_table", description="FAKE_TABLE not in KB")],
        confidence_notes=[ConfidenceNote(topic="x", confidence="low", rationale="couldn't verify")],
    )
    text = render_report(report)
    assert "Approved: False" in text
    assert "hallucinated_table" in text
    assert "FAKE_TABLE not in KB" in text
