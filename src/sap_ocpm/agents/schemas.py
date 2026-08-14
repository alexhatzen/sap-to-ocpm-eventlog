"""Shared pydantic schemas for the planner and critic agents."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Confidence = Literal["high", "medium", "low"]


class ActivityMapping(BaseModel):
    activity_name: str
    source_tables: list[str] = Field(
        default_factory=list, description="KB table names this activity is derived from"
    )
    notes: str = ""


class ConfidenceNote(BaseModel):
    topic: str
    confidence: Confidence
    rationale: str


class PlanGap(BaseModel):
    """A limitation the planner is already aware of and is surfacing
    up front, before construction — distinct from constructor.Gap,
    which is found during actual construction against real data."""

    category: str
    description: str


class ProcessPlan(BaseModel):
    """The planner's output: process scope decomposed BEFORE touching
    tables, reviewed and correctable by the user before anything
    downstream (construction) runs."""

    process_name: str
    process_description: str
    document_flow: list[str] = Field(
        description="Ordered stages of the document flow, e.g. "
        "['Requisition', 'Purchase Order', 'Goods Receipt', 'Invoice Verification', 'Payment']"
    )
    activities: list[ActivityMapping]
    case_granularity: Literal["item", "order"]
    case_granularity_rationale: str
    tables_referenced: list[str] = Field(
        description="Every KB table name the plan relies on — the critic checks each one "
        "actually exists in the KB"
    )
    known_gaps: list[PlanGap] = Field(default_factory=list)
    confidence_notes: list[ConfidenceNote] = Field(default_factory=list)


class CriticFinding(BaseModel):
    severity: Literal["error", "warning", "info"]
    category: str
    description: str


class CriticReport(BaseModel):
    """The critic's output: validates a ProcessPlan against the KB using
    only deterministic tools, flags gaps rather than smoothing over
    them, and states what it wasn't sure about."""

    approved: bool
    findings: list[CriticFinding] = Field(default_factory=list)
    confidence_notes: list[ConfidenceNote] = Field(default_factory=list)
