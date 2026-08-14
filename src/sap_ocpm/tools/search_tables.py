"""search_tables(keywords, module) — keyword retrieval over the KB.

Plain case-insensitive substring matching over table name, description,
typical_role, gotchas, and field names/descriptions. At 30 tables this
is sufficient; the README flags embeddings as the first upgrade once
the KB grows beyond a hand-curated size.
"""
from __future__ import annotations

from pydantic import BaseModel

from sap_ocpm.tools._shared import get_kb


class TableHit(BaseModel):
    table: str
    module: str
    description: str
    matched_on: list[str]


class SearchTablesResult(BaseModel):
    query_keywords: list[str]
    module_filter: str | None
    hits: list[TableHit]


def search_tables(keywords: str | list[str], module: str | None = None) -> SearchTablesResult:
    if isinstance(keywords, str):
        keywords = [keywords]
    keywords = [kw.strip().lower() for kw in keywords if kw.strip()]

    kb = get_kb()
    hits: list[TableHit] = []
    for table in kb:
        if module and table.module.lower() != module.lower():
            continue

        haystacks = {
            "name": table.name.lower(),
            "description": table.description.lower(),
            "typical_role": " ".join(table.typical_role).lower(),
            "gotchas": " ".join(table.gotchas).lower(),
            "field_names": " ".join(f.name for f in table.key_fields).lower(),
            "field_descriptions": " ".join(f.description for f in table.key_fields).lower(),
        }

        if not keywords:
            matched_on = ["module_filter_only"] if module else ["all"]
        else:
            matched_on = [
                field for field, text in haystacks.items()
                if any(kw in text for kw in keywords)
            ]
            if not matched_on:
                continue

        hits.append(
            TableHit(
                table=table.name,
                module=table.module,
                description=table.description,
                matched_on=matched_on,
            )
        )

    hits.sort(key=lambda h: h.table)
    return SearchTablesResult(query_keywords=keywords, module_filter=module, hits=hits)
