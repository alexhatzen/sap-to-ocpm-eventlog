"""Planner agent — decomposes a natural-language use case into process
scope BEFORE touching tables: which process, which document flow,
which activities constitute it, what case granularity fits. Emits a
ProcessPlan the user reviews and corrects before construction runs.

Tool access is deliberately limited to read-only KB retrieval
(search_tables, get_table_schema) — the planner reasons about scope,
it does not validate joins or SQL; that's the critic's job, later,
after the plan is approved.
"""
from __future__ import annotations

import json
import re

import claude_agent_sdk as sdk

from sap_ocpm.agents.schemas import ProcessPlan
from sap_ocpm.agents.sdk_tools import PLANNER_TOOLS, allowed_tool_names, build_server
from sap_ocpm.observability.trace import RunTrace, ToolCallRecord, finalize_trace, new_trace

SERVER_NAME = "sap_kb_planner"

SYSTEM_PROMPT = """\
You are the planning stage of an SAP-to-OCPM event log construction agent.

Your ONLY job here is process decomposition, not table selection detail
or event log construction. Given a natural-language use case, decompose
it into:
- process_name / process_description
- document_flow: the ordered stages of the P2P document flow this use
  case actually needs (not necessarily the full requisition-to-payment
  chain — scope it to what's asked)
- activities: the named process activities and which KB tables would
  plausibly evidence them
- case_granularity: "item" or "order", with a rationale grounded in the
  use case (not a default guess)
- tables_referenced: every table name you use anywhere in the plan
- known_gaps: anything you already suspect standard P2P tables can't
  give this analysis
- confidence_notes: what you're NOT sure about, with a stated confidence

HARD RULE: you MUST call search_tables and/or get_table_schema before
naming ANY table in your plan. If get_table_schema returns found=false,
that table does not exist in the KB — do not put it in your plan. Never
name a table from memory alone; this KB exists specifically so you
don't have to guess, and a plan with an invented table is worse than no
plan at all.

When you are done, output ONLY a fenced ```json code block containing a
single JSON object matching this exact shape (no prose after it):
{
  "process_name": str,
  "process_description": str,
  "document_flow": [str, ...],
  "activities": [{"activity_name": str, "source_tables": [str, ...], "notes": str}, ...],
  "case_granularity": "item" | "order",
  "case_granularity_rationale": str,
  "tables_referenced": [str, ...],
  "known_gaps": [{"category": str, "description": str}, ...],
  "confidence_notes": [{"topic": str, "confidence": "high"|"medium"|"low", "rationale": str}, ...]
}
"""


class PlannerError(RuntimeError):
    """Raised when the planner's output can't be trusted — malformed
    JSON, a schema mismatch, or no output at all. Never silently
    fall back to a fabricated ProcessPlan."""


def _extract_json_block(text: str) -> dict:
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = match.group(1) if match else text.strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise PlannerError(f"planner output was not valid JSON: {exc}\n---\n{text}") from exc


async def run_planner(use_case: str, *, model: str | None = None, max_turns: int = 12) -> tuple[ProcessPlan, RunTrace]:
    """Runs the planner agent. Returns (ProcessPlan, RunTrace) — the
    trace carries every tool call plus the SDK's own reported cost/usage
    for this run (see observability/trace.py)."""
    server = build_server(SERVER_NAME, PLANNER_TOOLS)
    options = sdk.ClaudeAgentOptions(
        max_turns=max_turns,
        model=model,
        mcp_servers={SERVER_NAME: server},
        allowed_tools=allowed_tool_names(SERVER_NAME, PLANNER_TOOLS),
        system_prompt=SYSTEM_PROMPT,
    )

    trace = new_trace("planner", use_case)
    final_text = ""
    result_msg = None

    async for msg in sdk.query(prompt=use_case, options=options):
        msg_type = type(msg).__name__
        if msg_type == "AssistantMessage":
            for block in msg.content:
                block_type = type(block).__name__
                if block_type == "ToolUseBlock":
                    trace.tool_calls.append(ToolCallRecord(tool=block.name, input=block.input))
                elif block_type == "TextBlock":
                    final_text += block.text
        elif msg_type == "ResultMessage":
            result_msg = msg

    finalize_trace(
        trace,
        num_turns=getattr(result_msg, "num_turns", None),
        total_cost_usd=getattr(result_msg, "total_cost_usd", None),
        usage=getattr(result_msg, "usage", None),
        result_text=final_text,
        is_error=getattr(result_msg, "is_error", False),
    )

    if not final_text.strip():
        raise PlannerError("planner produced no text output — check the trace for what happened instead")

    raw = _extract_json_block(final_text)
    try:
        plan = ProcessPlan.model_validate(raw)
    except Exception as exc:
        raise PlannerError(f"planner output did not match ProcessPlan schema: {exc}") from exc

    return plan, trace


def render_plan(plan: ProcessPlan) -> str:
    lines = [
        f"Process: {plan.process_name}",
        f"  {plan.process_description}",
        f"Document flow: {' -> '.join(plan.document_flow)}",
        f"Case granularity: {plan.case_granularity}  ({plan.case_granularity_rationale})",
        "Activities:",
    ]
    for a in plan.activities:
        lines.append(f"  - {a.activity_name}  [{', '.join(a.source_tables)}]  {a.notes}".rstrip())
    lines.append(f"Tables referenced: {', '.join(plan.tables_referenced)}")
    if plan.known_gaps:
        lines.append("Known gaps:")
        for g in plan.known_gaps:
            lines.append(f"  - [{g.category}] {g.description}")
    if plan.confidence_notes:
        lines.append("Confidence notes:")
        for c in plan.confidence_notes:
            lines.append(f"  - ({c.confidence}) {c.topic}: {c.rationale}")
    return "\n".join(lines)


def review_plan_interactive(plan: ProcessPlan) -> ProcessPlan | None:
    """The human review gate: prints the plan, prompts accept/edit/reject.
    Returns the (possibly hand-edited) plan, or None if rejected. This is
    a real interrupt, not a cosmetic confirmation — nothing downstream
    runs on a plan that hasn't passed through here.

    "Edit" drops the user into an editor on a JSON scratch file rather
    than a bespoke field-by-field prompt UI — simpler to build correctly,
    and consultants doing this kind of review are comfortable with JSON.
    """
    import subprocess
    import tempfile
    from pathlib import Path

    print(render_plan(plan))
    while True:
        choice = input("\n[a]ccept / [e]dit / [r]eject this plan? ").strip().lower()
        if choice.startswith("a"):
            return plan
        if choice.startswith("r"):
            return None
        if choice.startswith("e"):
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
                f.write(json.dumps(plan.model_dump(), indent=2))
                path = Path(f.name)
            editor = __import__("os").environ.get("EDITOR", "vi")
            subprocess.run([editor, str(path)])
            try:
                plan = ProcessPlan.model_validate(json.loads(path.read_text()))
            except Exception as exc:
                print(f"Edited plan failed validation: {exc}. Try again.")
            finally:
                path.unlink(missing_ok=True)
