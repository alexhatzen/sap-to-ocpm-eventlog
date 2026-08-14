"""Pydantic models for the grounded SAP table knowledge base.

Every table the agent is allowed to reference exists as a validated
`TableSpec` loaded from `kb/tables/*.yaml`. Nothing in this module ever
originates from an LLM: this is the retrieval substrate, not a shortcut
around it.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class TimestampGranularity(str, Enum):
    DATE_ONLY = "date_only"
    DATE_AND_TIME = "date_and_time"


class FieldSpec(BaseModel):
    """One documented field on a table."""

    name: str = Field(..., description="SAP field name, e.g. EBELN")
    description: str
    data_type: str = Field(..., description="SAP domain/type, e.g. CHAR(10), DEC(13,2), DATS")
    is_key: bool = Field(False, description="Part of the table's primary key")


class JoinEdge(BaseModel):
    """A declared, real foreign-key relationship. This is what makes
    find_join_path a graph search over facts instead of an LLM guess."""

    field: str = Field(..., description="Field on THIS table that carries the relationship")
    target_table: str
    target_field: str
    cardinality: str = Field(..., description="e.g. 'many_to_one', 'one_to_many', 'one_to_one'")
    notes: str = ""


class TimestampFieldSpec(BaseModel):
    """A date (and optionally time) field pair, with its resolution."""

    date_field: str
    time_field: str | None = None
    granularity: TimestampGranularity
    notes: str = ""


class TableSpec(BaseModel):
    """One curated table entry in the knowledge base."""

    name: str = Field(..., description="Table name, e.g. EKKO")
    module: str = Field(..., description="SAP module/area, e.g. MM, FI, Basis-ChangeDocs, Status-Mgmt")
    description: str
    key_fields: list[FieldSpec] = Field(default_factory=list)
    join_keys: list[JoinEdge] = Field(default_factory=list)
    typical_role: list[str] = Field(
        default_factory=list,
        description="Processes/activities this table typically evidences, e.g. 'PO creation', 'goods receipt'",
    )
    gotchas: list[str] = Field(default_factory=list)
    timestamp_fields: list[TimestampFieldSpec] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def name_is_upper(cls, v: str) -> str:
        if v != v.upper():
            raise ValueError(f"table name must be upper-case SAP style, got {v!r}")
        return v

    def field_names(self) -> set[str]:
        return {f.name for f in self.key_fields}
