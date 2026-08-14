"""Unit tests for the deterministic tools.

These tools are the layer where hallucination would be expensive and
where correctness must be structural, not probabilistic — so the tests
lean hard on the negative cases (undeclared tables, no-path joins,
malformed SQL, dangling event-log references) as much as the happy path.
"""
from __future__ import annotations

from sap_ocpm.tools import (
    check_event_log_spec,
    find_join_path,
    get_table_schema,
    search_tables,
    validate_sql,
)
from sap_ocpm.tools.check_event_log_spec import EventLogSpec


# --- get_table_schema -------------------------------------------------

def test_get_table_schema_found():
    result = get_table_schema("EKKO")
    assert result.found
    assert result.table.name == "EKKO"


def test_get_table_schema_hallucinated_table_reports_not_found():
    """The canary: EKKO_ITEM sounds plausible and does not exist."""
    result = get_table_schema("EKKO_ITEM")
    assert not result.found
    assert result.table is None
    assert "EKKO_ITEM" in result.error


def test_get_table_schema_is_case_insensitive():
    assert get_table_schema("ekko").found


# --- search_tables ------------------------------------------------------

def test_search_tables_finds_invoice_related_tables():
    result = search_tables("invoice")
    hit_names = {h.table for h in result.hits}
    assert "RBKP" in hit_names
    assert "RSEG" in hit_names


def test_search_tables_module_filter():
    result = search_tables("", module="MM-PUR")
    assert result.hits
    assert all(h.module == "MM-PUR" for h in result.hits)


def test_search_tables_no_match_returns_empty_not_a_guess():
    result = search_tables("totally_unrelated_keyword_zzz")
    assert result.hits == []


# --- find_join_path -------------------------------------------------

def test_find_join_path_known_chain():
    result = find_join_path("EKPO", "RBKP")
    assert result.found
    tables_touched = {result.from_table} | {s.to_table for s in result.steps}
    assert "RBKP" in tables_touched


def test_find_join_path_no_path_for_polymorphic_key_table():
    """CDHDR must never report a guessed path to EKKO — that's the
    whole point of not modeling OBJECTID as a clean FK."""
    result = find_join_path("CDHDR", "EKKO")
    assert not result.found
    assert result.steps == []
    assert result.reason


def test_find_join_path_unknown_table():
    result = find_join_path("NOT_A_REAL_TABLE", "EKKO")
    assert not result.found
    assert "not in knowledge base" in result.reason


def test_find_join_path_same_table_is_trivial():
    result = find_join_path("EKKO", "EKKO")
    assert result.found
    assert result.steps == []


# --- validate_sql -------------------------------------------------------

def test_validate_sql_accepts_well_formed_select():
    result = validate_sql("SELECT EBELN, BUKRS FROM EKKO WHERE LOEKZ = ''")
    assert result.valid


def test_validate_sql_rejects_keyword_typo_disguised_as_expression():
    """sqlglot's permissive parser turns 'SELEKT * FRM EKKO' into a
    legal arithmetic expression instead of raising — this must still
    be caught."""
    result = validate_sql("SELEKT * FRM EKKO")
    assert not result.valid
    assert result.errors


def test_validate_sql_rejects_empty_query():
    result = validate_sql("")
    assert not result.valid


def test_validate_sql_result_echoes_dialect_used():
    result = validate_sql("SELECT 1", dialect="postgres")
    assert result.dialect == "postgres"


# --- check_event_log_spec -----------------------------------------------

def _minimal_valid_spec() -> dict:
    return {
        "object_types": ["PurchaseOrder"],
        "event_types": ["Create PO"],
        "objects": [{"id": "PO1", "type": "PurchaseOrder"}],
        "events": [
            {
                "id": "E1",
                "type": "Create PO",
                "timestamp": "2019-01-01T10:00:00",
                "object_ids": ["PO1"],
            }
        ],
    }


def test_check_event_log_spec_valid_case():
    result = check_event_log_spec(_minimal_valid_spec())
    assert result.valid
    assert result.errors == []


def test_check_event_log_spec_catches_dangling_object_reference():
    spec = _minimal_valid_spec()
    spec["events"][0]["object_ids"] = ["GHOST_OBJECT"]
    result = check_event_log_spec(spec)
    assert not result.valid
    assert any("GHOST_OBJECT" in e for e in result.errors)


def test_check_event_log_spec_catches_undeclared_object_type():
    spec = _minimal_valid_spec()
    spec["objects"][0]["type"] = "NotDeclared"
    result = check_event_log_spec(spec)
    assert not result.valid


def test_check_event_log_spec_catches_bad_timestamp():
    spec = _minimal_valid_spec()
    spec["events"][0]["timestamp"] = "not-a-date"
    result = check_event_log_spec(spec)
    assert not result.valid
    assert any("ISO-8601" in e for e in result.errors)


def test_check_event_log_spec_accepts_typed_input_too():
    result = check_event_log_spec(EventLogSpec.model_validate(_minimal_valid_spec()))
    assert result.valid


def test_check_event_log_spec_warns_on_zero_events():
    spec = _minimal_valid_spec()
    spec["events"] = []
    result = check_event_log_spec(spec)
    assert result.valid
    assert any("zero events" in w for w in result.warnings)
