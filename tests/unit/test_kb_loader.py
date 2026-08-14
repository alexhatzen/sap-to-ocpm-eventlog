"""Unit tests for the knowledge-base loader — the load-bearing layer.

These tests exist to guarantee the KB fails loudly, not silently, when
it is internally inconsistent. A KB that loads "successfully" with a
dangling join is worse than one that refuses to load at all.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from sap_ocpm.kb.loader import KnowledgeBaseError, load_knowledge_base
from sap_ocpm.kb.schema import TableSpec

REAL_TABLES_DIR = Path(__file__).parents[2] / "src" / "sap_ocpm" / "kb" / "tables"


def test_real_kb_loads_and_has_at_least_thirty_tables():
    kb = load_knowledge_base(REAL_TABLES_DIR)
    assert len(kb) >= 30


def test_real_kb_every_join_target_exists():
    kb = load_knowledge_base(REAL_TABLES_DIR)
    for table in kb:
        for edge in table.join_keys:
            target = kb.get(edge.target_table)
            assert target is not None, f"{table.name}.{edge.field} points at undeclared {edge.target_table}"
            assert edge.target_field in target.field_names()


def test_real_kb_has_no_hallucinated_generic_key_joins():
    """CDHDR/CDPOS/JEST/NAST use polymorphic keys (OBJECTID/OBJNR/OBJKY)
    that must NOT be modeled as clean declared joins — that would be
    exactly the kind of plausible-looking fabrication this KB exists to
    prevent."""
    kb = load_knowledge_base(REAL_TABLES_DIR)
    cdhdr = kb.get("CDHDR")
    assert cdhdr is not None
    assert cdhdr.join_keys == [], "CDHDR.OBJECTID must not be declared as a clean FK"


def test_known_join_chain_ekpo_to_ekbe_to_rbkp():
    """EKPO -> EKBE -> RBKP is a real, declared 3-way-match chain."""
    kb = load_knowledge_base(REAL_TABLES_DIR)
    ekbe = kb.get("EKBE")
    targets = {edge.target_table for edge in ekbe.join_keys}
    assert "EKPO" in targets
    assert "RBKP" in targets
    assert "MKPF" in targets


def _write_table(tmp_path: Path, name: str, yaml_body: str) -> None:
    (tmp_path / f"{name}.yaml").write_text(textwrap.dedent(yaml_body))


def test_loader_rejects_join_to_nonexistent_table(tmp_path):
    _write_table(
        tmp_path,
        "AAAAA",
        """\
        name: AAAAA
        module: TEST
        description: test table
        key_fields:
          - {name: FOO, description: test field, data_type: "CHAR(1)", is_key: true}
        join_keys:
          - {field: FOO, target_table: DOES_NOT_EXIST, target_field: BAR, cardinality: many_to_one}
        """,
    )
    with pytest.raises(KnowledgeBaseError, match="undeclared table"):
        load_knowledge_base(tmp_path)


def test_loader_rejects_join_to_undeclared_field(tmp_path):
    _write_table(
        tmp_path,
        "AAAAA",
        """\
        name: AAAAA
        module: TEST
        description: test table
        key_fields:
          - {name: FOO, description: test field, data_type: "CHAR(1)", is_key: true}
        join_keys:
          - {field: FOO, target_table: BBBBB, target_field: NOT_A_FIELD, cardinality: many_to_one}
        """,
    )
    _write_table(
        tmp_path,
        "BBBBB",
        """\
        name: BBBBB
        module: TEST
        description: test table
        key_fields:
          - {name: BAR, description: test field, data_type: "CHAR(1)", is_key: true}
        """,
    )
    with pytest.raises(KnowledgeBaseError, match="not declared"):
        load_knowledge_base(tmp_path)


def test_loader_rejects_join_from_undeclared_source_field(tmp_path):
    _write_table(
        tmp_path,
        "AAAAA",
        """\
        name: AAAAA
        module: TEST
        description: test table
        key_fields:
          - {name: FOO, description: test field, data_type: "CHAR(1)", is_key: true}
        join_keys:
          - {field: NOT_A_SOURCE_FIELD, target_table: AAAAA, target_field: FOO, cardinality: many_to_one}
        """,
    )
    with pytest.raises(KnowledgeBaseError, match="undeclared source field"):
        load_knowledge_base(tmp_path)


def test_loader_rejects_filename_table_name_mismatch(tmp_path):
    _write_table(
        tmp_path,
        "AAAAA",
        """\
        name: WRONGNAME
        module: TEST
        description: test table
        key_fields: []
        """,
    )
    with pytest.raises(KnowledgeBaseError, match="file name must match"):
        load_knowledge_base(tmp_path)


def test_loader_rejects_empty_directory(tmp_path):
    with pytest.raises(KnowledgeBaseError, match="no table YAMLs"):
        load_knowledge_base(tmp_path)


def test_table_spec_rejects_lowercase_name():
    with pytest.raises(Exception):
        TableSpec(name="ekko", module="MM", description="x")
