"""Unit tests for observability (trace export + cost accounting) —
offline, using hand-built RunTrace objects rather than live agent runs.
"""
from __future__ import annotations

import json

from sap_ocpm.observability import (
    RunTrace,
    ToolCallRecord,
    export_trace,
    finalize_trace,
    new_trace,
    summarize_cost,
)


def _finished_trace(agent, cost, calls=None) -> RunTrace:
    t = new_trace(agent, "do something")
    t.tool_calls = calls or [ToolCallRecord(tool="get_table_schema", input={"table": "EKKO"})]
    finalize_trace(
        t, num_turns=3, total_cost_usd=cost, usage={"input_tokens": 100, "output_tokens": 50},
        result_text="done", is_error=False,
    )
    return t


def test_new_trace_has_started_at_and_no_end():
    t = new_trace("planner", "prompt")
    assert t.agent == "planner"
    assert t.started_at
    assert t.ended_at is None


def test_finalize_trace_populates_end_fields():
    t = _finished_trace("planner", 0.0123)
    assert t.ended_at is not None
    assert t.total_cost_usd == 0.0123
    assert t.num_turns == 3
    assert not t.is_error


def test_trace_to_dict_round_trips_tool_calls():
    t = _finished_trace("critic", 0.05)
    d = t.to_dict()
    assert d["tool_calls"] == [{"tool": "get_table_schema", "input": {"table": "EKKO"}}]
    assert d["total_cost_usd"] == 0.05


def test_trace_to_markdown_includes_cost_and_tool_calls():
    t = _finished_trace("planner", 0.02)
    md = t.to_markdown()
    assert "$0.0200" in md
    assert "get_table_schema" in md


def test_export_trace_writes_json_and_markdown(tmp_path):
    t = _finished_trace("planner", 0.01)
    json_path, md_path = export_trace(t, tmp_path)
    assert json_path.exists() and md_path.exists()
    data = json.loads(json_path.read_text())
    assert data["agent"] == "planner"
    assert "get_table_schema" in md_path.read_text()


def test_export_trace_does_not_clobber_successive_runs(tmp_path):
    t1 = _finished_trace("planner", 0.01)
    t1.started_at = "2024-01-01T00:00:00+00:00"
    t2 = _finished_trace("planner", 0.02)
    t2.started_at = "2024-01-01T00:00:01+00:00"
    p1, _ = export_trace(t1, tmp_path)
    p2, _ = export_trace(t2, tmp_path)
    assert p1 != p2
    assert p1.exists() and p2.exists()


def test_summarize_cost_aggregates_across_agents():
    traces = [_finished_trace("planner", 0.01), _finished_trace("critic", 0.02), _finished_trace("planner", 0.005)]
    summary = summarize_cost(traces)
    assert summary.n_runs == 3
    assert summary.total_cost_usd == 0.035
    assert summary.by_agent == {"planner": 0.015, "critic": 0.02}
    assert summary.unknown_cost_runs == 0


def test_summarize_cost_tracks_unknown_cost_runs_separately():
    t = new_trace("planner", "x")
    finalize_trace(t, num_turns=1, total_cost_usd=None, usage=None, result_text="", is_error=True)
    summary = summarize_cost([t])
    assert summary.unknown_cost_runs == 1
    assert summary.total_cost_usd == 0.0
