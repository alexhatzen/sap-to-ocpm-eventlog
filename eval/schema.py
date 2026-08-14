"""EvalCase — one hand-labeled use case for the eval harness.

expected_tables is the load-bearing field: "which tables would a
consultant actually pick for this use case." These need real domain
expertise, not a plausible guess — see cases/README.md for which cases
in this directory are genuinely expert-labeled vs. draft placeholders.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class EvalCase(BaseModel):
    id: str
    description: str
    use_case: str = Field(description="the natural-language prompt given to the planner")
    expected_tables: list[str] = Field(
        description="tables a domain expert would pick for this use case — the eval harness's ground truth"
    )
    notes: str = ""
    is_draft: bool = Field(
        default=True,
        description="True until a domain expert has actually reviewed expected_tables — "
        "draft cases are excluded from the headline results table by default.",
    )
