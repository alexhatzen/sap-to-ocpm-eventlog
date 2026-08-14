"""RunTrace — a full, readable record of every tool call and the final
cost/usage for one agent run (planner or critic).

Design note: cost is taken directly from the Claude Agent SDK's own
ResultMessage.total_cost_usd/usage, not recomputed from a hand-maintained
price list. A hardcoded pricing table would go stale the moment prices
change — the SDK/CLI already knows the real, current cost of the run it
just made, so that's the source of truth used here instead.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class ToolCallRecord:
    tool: str
    input: dict


@dataclass
class RunTrace:
    agent: str  # "planner" | "critic"
    prompt: str
    started_at: str
    ended_at: str | None = None
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    num_turns: int | None = None
    total_cost_usd: float | None = None
    usage: dict | None = None
    result_text: str = ""
    is_error: bool = False

    def to_dict(self) -> dict:
        return {
            "agent": self.agent,
            "prompt": self.prompt,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "tool_calls": [{"tool": c.tool, "input": c.input} for c in self.tool_calls],
            "num_turns": self.num_turns,
            "total_cost_usd": self.total_cost_usd,
            "usage": self.usage,
            "result_text": self.result_text,
            "is_error": self.is_error,
        }

    def to_markdown(self) -> str:
        lines = [
            f"# {self.agent} run trace",
            "",
            f"- started: {self.started_at}",
            f"- ended: {self.ended_at}",
            f"- turns: {self.num_turns}",
            f"- cost: ${self.total_cost_usd:.4f}" if self.total_cost_usd is not None else "- cost: unknown",
            f"- error: {self.is_error}",
            "",
            f"## Prompt",
            self.prompt,
            "",
            f"## Tool calls ({len(self.tool_calls)})",
        ]
        for i, call in enumerate(self.tool_calls, 1):
            lines.append(f"{i}. `{call.tool}`  {json.dumps(call.input)}")
        return "\n".join(lines)


def new_trace(agent: str, prompt: str) -> RunTrace:
    return RunTrace(agent=agent, prompt=prompt, started_at=datetime.now(timezone.utc).isoformat())


def finalize_trace(trace: RunTrace, *, num_turns, total_cost_usd, usage, result_text, is_error) -> RunTrace:
    trace.ended_at = datetime.now(timezone.utc).isoformat()
    trace.num_turns = num_turns
    trace.total_cost_usd = total_cost_usd
    trace.usage = usage
    trace.result_text = result_text
    trace.is_error = is_error
    return trace


def export_trace(trace: RunTrace, directory: Path | str) -> tuple[Path, Path]:
    """Writes both a JSON and a readable markdown export for one run,
    named by agent + timestamp so successive runs don't clobber each other."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = trace.started_at.replace(":", "").replace("+00:00", "Z")
    json_path = directory / f"{trace.agent}_{stamp}.json"
    md_path = directory / f"{trace.agent}_{stamp}.md"
    json_path.write_text(json.dumps(trace.to_dict(), indent=2))
    md_path.write_text(trace.to_markdown())
    return json_path, md_path
