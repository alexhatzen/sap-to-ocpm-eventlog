"""Shared data structures for the event log constructor."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ActivityEvent:
    """One derived activity instance, before OCEL assembly."""

    ebeln: str
    ebelp: str | None  # None for header-level activities
    activity: str
    timestamp: str | None  # ISO 8601, or None if undated (see gap_flagging)
    source_table: str
    sequence: int  # original derivation order — used only as a final sort tiebreak
    user: str = ""
    extra: dict | None = None


@dataclass
class Gap:
    """A known limitation surfaced to the caller instead of silently
    papered over — timestamp_resolution/gap_flagging populate these."""

    category: str
    description: str
    ebeln: str | None = None
    ebelp: str | None = None
