"""get_table_schema(table) — direct, deterministic KB lookup.

Never guesses at a schema. If the table isn't in the KB, the result
says so explicitly (`found=False`) instead of returning something that
looks plausible.
"""
from __future__ import annotations

from pydantic import BaseModel

from sap_ocpm.kb.schema import TableSpec
from sap_ocpm.tools._shared import get_kb


class TableSchemaResult(BaseModel):
    found: bool
    table: TableSpec | None = None
    error: str | None = None


def get_table_schema(table: str) -> TableSchemaResult:
    kb = get_kb()
    spec = kb.get(table)
    if spec is None:
        return TableSchemaResult(
            found=False,
            error=(
                f"{table!r} is not in the knowledge base. Known tables: "
                f"{', '.join(sorted(kb.tables))}. This is not necessarily wrong — "
                f"the KB is deliberately scoped to ~30 P2P tables — but do not "
                f"assume the table exists or invent its schema."
            ),
        )
    return TableSchemaResult(found=True, table=spec)
