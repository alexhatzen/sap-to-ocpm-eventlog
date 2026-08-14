"""gap_flagging — surfaces where the requested analysis needs data the
raw tables (real SAP or this fixture) don't retain, instead of
fabricating a value. Combines the structural gaps activity_derivation
already found (unresolved joins, ambiguous attribution) with a few
additional checks over the finished case set.
"""
from __future__ import annotations

from sap_ocpm.constructor.schemas import ActivityEvent, Gap


def flag_additional_gaps(events: list[ActivityEvent]) -> list[Gap]:
    gaps: list[Gap] = []

    undated = [e for e in events if e.timestamp is None]
    if undated:
        gaps.append(Gap(
            category="undated_events",
            description=(
                f"{len(undated)} event(s) had no parseable date and were sorted last rather "
                f"than assigned a fabricated timestamp — check source rows for missing "
                f"UDATE/BUDAT/CPUDT values before trusting duration metrics involving them."
            ),
        ))

    placeholder_qty_activities = {"Record Goods Receipt"}
    if any(e.activity in placeholder_qty_activities for e in events):
        gaps.append(Gap(
            category="known_limitation",
            description=(
                "Goods-receipt quantity (MSEG.MENGE) is a placeholder value in this "
                "BPI2019-derived fixture, not a real received quantity — BPI2019 exposes only "
                "a running 'Cumulative net worth (EUR)' figure at the event level, not "
                "item-level quantities. Do not use MENGE from this fixture for quantity-based "
                "3-way-match analysis; DMBTR (amount) is grounded in the real data instead."
            ),
        ))

    return gaps
