"""Critic agent — validates a ProcessPlan against the knowledge base
using ONLY deterministic tools, before construction runs. It has no
authority to fix anything itself: it flags gaps and states its own
uncertainty rather than smoothing either over.

Checks it's asked to specifically perform: every table in the plan
exists in the KB, every join implied by the activities has a real
declared path, the plan's case_granularity is internally consistent
with its own rationale. It composes get_table_schema and
find_join_path itself rather than being told the answers, so its
approval is grounded in the same tools an engineer would use by hand.
"""
from __future__ import annotations

import json
import re

import claude_agent_sdk as sdk

from sap_ocpm.agents.schemas import CriticReport, ProcessPlan
from sap_ocpm.agents.sdk_tools import CRITIC_TOOLS, allowed_tool_names, build_server
from sap_ocpm.observability.trace import RunTrace, ToolCallRecord, finalize_trace, new_trace

SERVER_NAME = "sap_kb_critic"

SYSTEM_PROMPT = """\
You are the critic stage of an SAP-to-OCPM event log construction agent.
You review a ProcessPlan the planner already produced. You do NOT trust
the planner's table names or join claims — verify every one yourself
using get_table_schema and find_join_path before approving anything.

For every table in plan.tables_referenced: call get_table_schema. If
found=false for any table, that is an "error" severity finding — the
plan references a table that doesn't exist in the KB, and this is
exactly the hallucination this whole project exists to catch.

For every pair of tables that plausibly need to be joined to support an
activity in the plan, call find_join_path. If found=false, that is at
least a "warning" — the plan implies a join that has no declared path
(this is CORRECT and expected for tables with polymorphic keys like
CDHDR/JEST/NAST; say so in the finding rather than treating it as
automatically fatal, but do flag it so a human knows to check).

Set approved=true only if there are no "error" severity findings.
State your own uncertainty honestly in confidence_notes — do not claim
high confidence about something you didn't actually verify with a tool
call.

When you are done, output ONLY a fenced ```json code block containing a
single JSON object matching this exact shape (no prose after it):
{
  "approved": bool,
  "findings": [{"severity": "error"|"warning"|"info", "category": str, "description": str}, ...],
  "confidence_notes": [{"topic": str, "confidence": "high"|"medium"|"low", "rationale": str}, ...]
}
"""


class CriticError(RuntimeError):
    """Raised when the critic's output can't be trusted. Never silently
    fall back to a fabricated approval."""


def _extract_json_block(text: str) -> dict:
    match = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = match.group(1) if match else text.strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise CriticError(f"critic output was not valid JSON: {exc}\n---\n{text}") from exc


async def run_critic(plan: ProcessPlan, *, model: str | None = None, max_turns: int = 20) -> tuple[CriticReport, RunTrace]:
    server = build_server(SERVER_NAME, CRITIC_TOOLS)
    options = sdk.ClaudeAgentOptions(
        max_turns=max_turns,
        model=model,
        mcp_servers={SERVER_NAME: server},
        allowed_tools=allowed_tool_names(SERVER_NAME, CRITIC_TOOLS),
        system_prompt=SYSTEM_PROMPT,
    )

    prompt = f"Review this ProcessPlan:\n\n{json.dumps(plan.model_dump(), indent=2)}"
    trace = new_trace("critic", prompt)
    final_text = ""
    result_msg = None

    async for msg in sdk.query(prompt=prompt, options=options):
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
        raise CriticError("critic produced no text output — check the trace for what happened instead")

    raw = _extract_json_block(final_text)
    try:
        report = CriticReport.model_validate(raw)
    except Exception as exc:
        raise CriticError(f"critic output did not match CriticReport schema: {exc}") from exc

    return report, trace


def render_report(report: CriticReport) -> str:
    lines = [f"Approved: {report.approved}", "Findings:"]
    for f in report.findings:
        lines.append(f"  [{f.severity}] ({f.category}) {f.description}")
    if report.confidence_notes:
        lines.append("Confidence notes:")
        for c in report.confidence_notes:
            lines.append(f"  - ({c.confidence}) {c.topic}: {c.rationale}")
    return "\n".join(lines)
