"""Loads and validates the table knowledge base.

Fails loudly at import/load time if the KB is internally inconsistent
(a join pointing at a table or field that doesn't exist). That is the
whole point: `find_join_path` is only trustworthy if every edge in the
graph is guaranteed to resolve to something real.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from sap_ocpm.kb.schema import TableSpec

DEFAULT_TABLES_DIR = Path(__file__).parent / "tables"


class KnowledgeBaseError(ValueError):
    """Raised when the KB fails self-validation. This must never be
    silently swallowed — a broken KB means every downstream tool is
    operating on unverified ground."""


@dataclass(frozen=True)
class KnowledgeBase:
    tables: dict[str, TableSpec]

    def __contains__(self, table_name: str) -> bool:
        return table_name.upper() in self.tables

    def get(self, table_name: str) -> TableSpec | None:
        return self.tables.get(table_name.upper())

    def __iter__(self):
        return iter(self.tables.values())

    def __len__(self) -> int:
        return len(self.tables)


def load_knowledge_base(tables_dir: Path | str = DEFAULT_TABLES_DIR) -> KnowledgeBase:
    tables_dir = Path(tables_dir)
    yaml_files = sorted(tables_dir.glob("*.yaml"))
    if not yaml_files:
        raise KnowledgeBaseError(f"no table YAMLs found under {tables_dir}")

    tables: dict[str, TableSpec] = {}
    for path in yaml_files:
        raw = yaml.safe_load(path.read_text())
        try:
            spec = TableSpec.model_validate(raw)
        except Exception as exc:  # re-raise with file context, don't hide the source
            raise KnowledgeBaseError(f"{path.name}: failed schema validation: {exc}") from exc

        expected_stem = path.stem.upper()
        if spec.name != expected_stem:
            raise KnowledgeBaseError(
                f"{path.name}: file name must match table name, got name={spec.name!r}"
            )
        if spec.name in tables:
            raise KnowledgeBaseError(f"duplicate table definition for {spec.name}")
        tables[spec.name] = spec

    _validate_join_graph(tables)
    return KnowledgeBase(tables=tables)


def _validate_join_graph(tables: dict[str, TableSpec]) -> None:
    """Every join_key must point at a table and field that actually
    exist in the KB. This is the check that makes find_join_path
    correct by construction rather than best-effort."""
    errors: list[str] = []
    for table in tables.values():
        source_fields = table.field_names()
        for edge in table.join_keys:
            if edge.field not in source_fields:
                errors.append(
                    f"{table.name}: join_keys references undeclared source field {edge.field!r}"
                )
            target = tables.get(edge.target_table.upper())
            if target is None:
                errors.append(
                    f"{table.name}: join to undeclared table {edge.target_table!r} "
                    f"(add it to the KB or fix the typo — never leave a dangling join)"
                )
                continue
            if edge.target_field not in target.field_names():
                errors.append(
                    f"{table.name}.{edge.field} -> {edge.target_table}: "
                    f"target field {edge.target_field!r} not declared on {edge.target_table}"
                )
    if errors:
        raise KnowledgeBaseError(
            "knowledge base failed join-graph validation:\n  " + "\n  ".join(errors)
        )
