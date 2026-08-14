"""Wraps this project's deterministic tools (src/sap_ocpm/tools/) as
Claude Agent SDK in-process MCP tools.

This module contains zero decision logic of its own — it's plumbing.
Each SDK tool is a thin adapter calling straight into the same plain
Python functions used everywhere else (and unit-tested in isolation in
tests/unit/test_tools.py). The planner and critic agents get scoped,
different subsets of these tools, matching the plan's "which parts to
not hand to the model" boundary.
"""
from __future__ import annotations

import claude_agent_sdk as sdk

from sap_ocpm.tools import (
    check_event_log_spec,
    find_join_path,
    get_table_schema,
    search_tables,
    validate_sql,
)


@sdk.tool(
    "search_tables",
    "Search the grounded SAP P2P knowledge base by keyword and/or module. "
    "Returns only tables that actually exist in the KB — never invent a table name "
    "that hasn't shown up in a search_tables or get_table_schema result.",
    {"keywords": str, "module": str},
)
async def _search_tables_tool(args: dict) -> dict:
    result = search_tables(args.get("keywords", ""), args.get("module") or None)
    return {"content": [{"type": "text", "text": result.model_dump_json(indent=2)}]}


@sdk.tool(
    "get_table_schema",
    "Look up the full schema (fields, declared joins, gotchas, timestamp fields) "
    "for one table name in the knowledge base. If found=false, the table does not "
    "exist in this KB — do not reference it in your plan.",
    {"table": str},
)
async def _get_table_schema_tool(args: dict) -> dict:
    result = get_table_schema(args["table"])
    return {"content": [{"type": "text", "text": result.model_dump_json(indent=2)}]}


@sdk.tool(
    "find_join_path",
    "Find the declared join path between two KB tables via graph search over real "
    "foreign keys. If found=false, there is no declared join — do not invent one, "
    "even if it seems plausible (this is deliberate for tables with polymorphic "
    "keys like CDHDR/JEST/NAST).",
    {"table_a": str, "table_b": str},
)
async def _find_join_path_tool(args: dict) -> dict:
    result = find_join_path(args["table_a"], args["table_b"])
    return {"content": [{"type": "text", "text": result.model_dump_json(indent=2)}]}


@sdk.tool(
    "validate_sql",
    "Parse and structurally validate a SQL query (syntax only, not KB awareness).",
    {"query": str},
)
async def _validate_sql_tool(args: dict) -> dict:
    result = validate_sql(args["query"])
    return {"content": [{"type": "text", "text": result.model_dump_json(indent=2)}]}


@sdk.tool(
    "check_event_log_spec",
    "Structurally validate an OCEL-shaped event log spec (JSON object with "
    "object_types, event_types, objects, events) — declared types, ISO-8601 "
    "timestamps, no dangling object references.",
    {"spec_json": str},
)
async def _check_event_log_spec_tool(args: dict) -> dict:
    import json

    spec = json.loads(args["spec_json"])
    result = check_event_log_spec(spec)
    return {"content": [{"type": "text", "text": result.model_dump_json(indent=2)}]}


PLANNER_TOOLS = [_search_tables_tool, _get_table_schema_tool]
CRITIC_TOOLS = [_get_table_schema_tool, _find_join_path_tool, _check_event_log_spec_tool]
ALL_TOOLS = [
    _search_tables_tool,
    _get_table_schema_tool,
    _find_join_path_tool,
    _validate_sql_tool,
    _check_event_log_spec_tool,
]


def build_server(name: str, tools: list):
    return sdk.create_sdk_mcp_server(name, tools=tools)


def allowed_tool_names(server_name: str, tools: list) -> list[str]:
    return [f"mcp__{server_name}__{t.name}" for t in tools]
