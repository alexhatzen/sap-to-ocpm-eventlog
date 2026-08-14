"""case_granularity — order-level vs item-level case-ID construction,
and the concrete consequence of each choice.

Item-level (EBELN+EBELP) is the default: it matches BPI2019's own
native case notion, and it's the granularity at which most P2P
questions ("how long from PO item creation to invoice receipt") are
actually asked. Order-level (EBELN) rolls items up into one case per
purchase order — coarser, but it's the only granularity at which the
CDHDR/CDPOS proxy events on multi-item POs (see activity_derivation's
`ambiguous_item_attribution` gap) can be included at all, since they
genuinely cannot be attributed to one item.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Literal

from sap_ocpm.constructor.schemas import ActivityEvent
from sap_ocpm.constructor.timestamp_resolution import sort_key

Granularity = Literal["item", "order"]


def case_id(event: ActivityEvent, granularity: Granularity) -> str | None:
    """Returns the case id this event belongs to at the given
    granularity, or None if the event cannot be assigned one (vendor-only
    clearing events with no EBELN at all — excluded from PO-object cases
    at any granularity, see activity_derivation's known_limitation gap)."""
    if not event.ebeln:
        return None
    if granularity == "order":
        return event.ebeln
    # item-level: header-only (ebelp=None) events are excluded — real ambiguity
    if event.ebelp is None:
        return None
    return f"{event.ebeln}_{event.ebelp}"


def build_cases(events: list[ActivityEvent], granularity: Granularity) -> dict[str, list[ActivityEvent]]:
    cases: dict[str, list[ActivityEvent]] = defaultdict(list)
    for event in events:
        cid = case_id(event, granularity)
        if cid is not None:
            cases[cid].append(event)

    for case_events in cases.values():
        case_events.sort(key=sort_key)

    return dict(cases)
