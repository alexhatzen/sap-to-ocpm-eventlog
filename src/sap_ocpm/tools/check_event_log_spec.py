"""check_event_log_spec(spec) — structural validation of an OCEL-style
event log spec/output.

Deterministic, schema-level checks only: declared object types are
consistent, timestamps are ISO-parseable, and every reference from an
event to an object points at something that actually exists. This is
NOT a check that the *content* is correct (that's the critic agent's
job, using this tool as one of its building blocks) — it's the
structural floor every event log must clear before anything gets built
on top of it.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class OcelObject(BaseModel):
    id: str
    type: str


class OcelEvent(BaseModel):
    id: str
    type: str
    timestamp: str
    object_ids: list[str] = Field(default_factory=list)


class EventLogSpec(BaseModel):
    """Minimal OCEL-2.0-shaped structure sufficient for structural checks."""

    object_types: list[str]
    event_types: list[str]
    objects: list[OcelObject]
    events: list[OcelEvent]


class SpecCheckResult(BaseModel):
    valid: bool
    errors: list[str] = []
    warnings: list[str] = []
    object_count: int = 0
    event_count: int = 0


def check_event_log_spec(spec: EventLogSpec | dict) -> SpecCheckResult:
    if isinstance(spec, dict):
        try:
            spec = EventLogSpec.model_validate(spec)
        except Exception as exc:
            return SpecCheckResult(valid=False, errors=[f"spec failed schema validation: {exc}"])

    errors: list[str] = []
    warnings: list[str] = []

    declared_object_types = set(spec.object_types)
    declared_event_types = set(spec.event_types)
    object_ids = {obj.id for obj in spec.objects}

    if len(object_ids) != len(spec.objects):
        errors.append("duplicate object ids present — case/object identity is not unique")

    for obj in spec.objects:
        if obj.type not in declared_object_types:
            errors.append(f"object {obj.id!r} has undeclared type {obj.type!r}")

    event_ids = [e.id for e in spec.events]
    if len(set(event_ids)) != len(event_ids):
        errors.append("duplicate event ids present")

    for event in spec.events:
        if event.type not in declared_event_types:
            errors.append(f"event {event.id!r} has undeclared type {event.type!r}")

        try:
            datetime.fromisoformat(event.timestamp)
        except ValueError:
            errors.append(f"event {event.id!r} has a non-ISO-8601 timestamp: {event.timestamp!r}")

        if not event.object_ids:
            warnings.append(f"event {event.id!r} is not linked to any object — check this is intentional for an object-centric log")

        for oid in event.object_ids:
            if oid not in object_ids:
                errors.append(f"event {event.id!r} references undeclared object id {oid!r}")

    if not spec.events:
        warnings.append("event log has zero events")

    return SpecCheckResult(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        object_count=len(spec.objects),
        event_count=len(spec.events),
    )
