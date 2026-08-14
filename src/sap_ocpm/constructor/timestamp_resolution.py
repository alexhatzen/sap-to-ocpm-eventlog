"""timestamp_resolution — SAP splits date and time across fields
(ERDAT/ERZET, CPUDT/CPUTM, ...), and several tables in this KB carry
date only. This module states, in code, the tie-break/ordering rules
so two runs never silently produce a pile of events sharing one
timestamp with no defined order.

Rule: prefer a real date+time pair when one exists (CPUDT/CPUTM,
UDATE/UTIME) over a date-only field (BUDAT, AEDAT, ERDAT) — this
mirrors the `timestamp_fields` granularity already declared per table
in the KB. When two events land on the exact same timestamp (common
for batch-posted BPI2019 events, e.g. multiple SRM steps stamped to
the same minute), ties are broken by a documented, stable source-table
priority, then by insertion order — never left to whatever order a
dict/DB happened to return.
"""
from __future__ import annotations

from datetime import datetime

# Lower number = higher confidence in the timestamp's real ordering
# precision, used only to break exact timestamp ties deterministically.
SOURCE_PRIORITY = {
    "CDHDR": 0,   # UDATE+UTIME, logged at the moment of the change
    "EKBE": 1,    # CPUDT+CPUTM, system entry timestamp
    "RBKP": 1,
    "BKPF": 1,
    "MKPF": 1,
}
DEFAULT_PRIORITY = 5


def resolve_timestamp(date_field: str, time_field: str | None = None) -> str | None:
    """Combines an 8-digit SAP DATS and optional 6-digit TIMS into ISO 8601.
    Returns None if the date is missing/unparseable rather than fabricating
    a fake midnight timestamp that would silently misorder the log."""
    if not date_field or len(date_field) != 8:
        return None
    try:
        year, month, day = int(date_field[:4]), int(date_field[4:6]), int(date_field[6:8])
        if time_field and len(time_field) == 6:
            hour, minute, second = int(time_field[:2]), int(time_field[2:4]), int(time_field[4:6])
        else:
            hour = minute = second = 0
        return datetime(year, month, day, hour, minute, second).isoformat()
    except ValueError:
        return None


def sort_key(event) -> tuple:
    """Stable sort key: (timestamp, source-table priority, insertion index).
    `event` must expose `.timestamp` (ISO string or None), `.source_table`,
    and `.sequence` (original derivation order, used as the final tiebreak
    so the sort is always deterministic even across same-priority ties)."""
    ts = event.timestamp or "9999-12-31T23:59:59"  # undated events sort last, never silently dropped
    priority = SOURCE_PRIORITY.get(event.source_table, DEFAULT_PRIORITY)
    return (ts, priority, event.sequence)
