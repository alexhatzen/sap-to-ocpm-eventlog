"""ocel_writer — assembles derived activities into an OCEL 2.0-shaped
event log (PurchaseOrder/PurchaseOrderItem/Vendor object types) and
validates the result with the same check_event_log_spec tool the
critic agent will use later — the constructor holds itself to the
exact same structural bar, not a looser one.
"""
from __future__ import annotations

import json
from pathlib import Path

from sap_ocpm.constructor.case_granularity import Granularity, case_id
from sap_ocpm.constructor.schemas import ActivityEvent
from sap_ocpm.constructor.timestamp_resolution import sort_key
from sap_ocpm.tools.check_event_log_spec import (
    EventLogSpec,
    OcelEvent,
    OcelObject,
    SpecCheckResult,
    check_event_log_spec,
)

OBJECT_TYPE_PO = "PurchaseOrder"
OBJECT_TYPE_ITEM = "PurchaseOrderItem"
OBJECT_TYPE_VENDOR = "Vendor"


def build_ocel(
    events: list[ActivityEvent],
    granularity: Granularity,
    vendors: dict[str, str] | None = None,
) -> EventLogSpec:
    """`vendors` optionally maps LIFNR -> name for BSEG-only vendor
    objects that have no PurchaseOrder to hang off of."""
    vendors = vendors or {}

    objects: dict[str, OcelObject] = {}
    object_types: set[str] = set()
    event_types: set[str] = set()
    ocel_events: list[OcelEvent] = []

    sorted_events = sorted(
        (e for e in events if e.timestamp is not None or True), key=sort_key
    )

    for i, event in enumerate(sorted_events):
        event_types.add(event.activity)
        related_object_ids: list[str] = []

        if event.ebeln:
            po_id = f"PO:{event.ebeln}"
            if po_id not in objects:
                objects[po_id] = OcelObject(id=po_id, type=OBJECT_TYPE_PO)
                object_types.add(OBJECT_TYPE_PO)
            related_object_ids.append(po_id)

            cid = case_id(event, granularity)
            if granularity == "item" and cid is not None:
                item_id = f"ITEM:{cid}"
                if item_id not in objects:
                    objects[item_id] = OcelObject(id=item_id, type=OBJECT_TYPE_ITEM)
                    object_types.add(OBJECT_TYPE_ITEM)
                related_object_ids.append(item_id)

        vendor_lifnr = (event.extra or {}).get("vendor") if event.extra else None
        if vendor_lifnr:
            vendor_id = f"VENDOR:{vendor_lifnr}"
            if vendor_id not in objects:
                objects[vendor_id] = OcelObject(id=vendor_id, type=OBJECT_TYPE_VENDOR)
                object_types.add(OBJECT_TYPE_VENDOR)
            related_object_ids.append(vendor_id)

        if not related_object_ids:
            continue  # an event related to nothing is not a valid OCEL event — drop, don't fabricate a relation

        ocel_events.append(OcelEvent(
            id=f"E{i+1}",
            type=event.activity,
            timestamp=event.timestamp or "9999-12-31T23:59:59",
            object_ids=related_object_ids,
        ))

    return EventLogSpec(
        object_types=sorted(object_types),
        event_types=sorted(event_types),
        objects=list(objects.values()),
        events=ocel_events,
    )


def validate_ocel(spec: EventLogSpec) -> SpecCheckResult:
    return check_event_log_spec(spec)


def write_ocel_json(spec: EventLogSpec, path: Path | str) -> None:
    Path(path).write_text(json.dumps(spec.model_dump(), indent=2))
