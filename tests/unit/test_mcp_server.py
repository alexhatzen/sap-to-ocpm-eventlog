"""Unit tests for the MCP server — registration and tool execution,
against the real checked-in fixture (offline, no network/stdio needed;
FastMCP's list_tools()/call_tool() work in-process)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sap_ocpm.interfaces import mcp_server
from sap_ocpm.interfaces.mcp_server import server

FIXTURE_DIR = Path(__file__).parents[2] / "data" / "fixtures" / "bpi2019_sample"


def test_all_expected_tools_are_registered():
    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    assert names == {
        "search_tables_tool", "get_table_schema_tool", "find_join_path_tool",
        "validate_sql_tool", "check_event_log_spec_tool", "build_event_log",
    }


def _call(name, args):
    result = asyncio.run(server.call_tool(name, args))
    return json.loads(result[0].text) if isinstance(result, tuple) else json.loads(result[0].text)


def test_get_table_schema_tool_hallucination_canary():
    data = _call("get_table_schema_tool", {"table": "EKKO_ITEM"})
    assert data["found"] is False


def test_get_table_schema_tool_real_table():
    data = _call("get_table_schema_tool", {"table": "EKKO"})
    assert data["found"] is True
    assert data["table"]["name"] == "EKKO"


def test_find_join_path_tool_no_guessed_join():
    data = _call("find_join_path_tool", {"table_a": "CDHDR", "table_b": "EKKO"})
    assert data["found"] is False


def test_validate_sql_tool():
    data = _call("validate_sql_tool", {"query": "SELECT EBELN FROM EKKO"})
    assert data["valid"] is True


def test_check_event_log_spec_tool_dangling_reference():
    spec = {
        "object_types": ["PurchaseOrder"], "event_types": ["Create PO"],
        "objects": [{"id": "PO1", "type": "PurchaseOrder"}],
        "events": [{"id": "E1", "type": "Create PO", "timestamp": "2019-01-01T00:00:00", "object_ids": ["GHOST"]}],
    }
    data = _call("check_event_log_spec_tool", {"spec_json": json.dumps(spec)})
    assert data["valid"] is False


def test_build_event_log_against_real_fixture():
    data = _call("build_event_log", {"fixture_dir": str(FIXTURE_DIR), "granularity": "item"})
    assert data["n_events_derived"] > 1000
    assert data["ocel_validation"]["valid"] is True
    assert len(data["gaps"]) > 0
    assert "PurchaseOrderItem" in data["object_types"]


def test_build_event_log_writes_output_file(tmp_path, monkeypatch):
    # output_path is confined to ALLOWED_ROOT (see hardening tests below) —
    # monkeypatch it to tmp_path so this test can write there without
    # littering the real repo tree, using a minimal synthetic fixture
    # instead of the real one (also outside the real ALLOWED_ROOT otherwise).
    monkeypatch.setattr(mcp_server, "ALLOWED_ROOT", tmp_path)
    fixture_dir = tmp_path / "fixture"
    fixture_dir.mkdir()
    (fixture_dir / "ekpo.csv").write_text("EBELN,EBELP\nPO1,00001\n")
    out = tmp_path / "log.json"

    data = _call(
        "build_event_log",
        {"fixture_dir": str(fixture_dir), "granularity": "order", "output_path": str(out)},
    )
    assert data.get("error") is None, data.get("error")
    assert data["output_written_to"] == str(out)
    assert out.exists()
    written = json.loads(out.read_text())
    assert "PurchaseOrderItem" not in written["object_types"]  # order granularity


# --- path-restriction hardening -----------------------------------------

def test_build_event_log_rejects_fixture_dir_outside_allowed_root(tmp_path):
    outside = tmp_path / "not_in_repo"
    outside.mkdir()
    data = _call("build_event_log", {"fixture_dir": str(outside)})
    assert "error" in data
    assert "outside the allowed directory" in data["error"]


def test_build_event_log_rejects_output_path_outside_allowed_root(tmp_path):
    outside_output = tmp_path / "evil.json"
    data = _call(
        "build_event_log",
        {"fixture_dir": str(FIXTURE_DIR), "granularity": "order", "output_path": str(outside_output)},
    )
    assert "error" in data
    assert "outside the allowed directory" in data["error"]
    assert not outside_output.exists()  # never written


def test_build_event_log_rejects_traversal_via_relative_path():
    data = _call("build_event_log", {"fixture_dir": "../../../../../../etc"})
    assert "error" in data


def test_resolve_within_allowed_root_accepts_relative_path_inside_root():
    resolved = mcp_server._resolve_within_allowed_root(
        "data/fixtures/bpi2019_sample", purpose="fixture_dir"
    )
    assert resolved == FIXTURE_DIR.resolve()
