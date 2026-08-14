"""MCP server — drops this project's deterministic tools (and the
end-to-end constructor pipeline) into Claude Desktop, Cursor, or any
other MCP client. Uses the official `mcp` Python SDK's FastMCP, which
is a separate thing from claude_agent_sdk's in-process SDK-MCP server
used internally by the planner/critic agents (agents/sdk_tools.py) —
this one is a real standalone server process for external clients.

Run directly: `python3 -m sap_ocpm.interfaces.mcp_server` (stdio transport).
"""
from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from sap_ocpm.constructor import (
    build_cases,
    build_ocel,
    derive_activities,
    flag_additional_gaps,
    load_tables_from_fixture,
    validate_ocel,
)
from sap_ocpm.tools import (
    check_event_log_spec,
    find_join_path,
    get_table_schema,
    search_tables,
    validate_sql,
)

# build_event_log's fixture_dir/output_path are free-text paths supplied by
# whatever's driving the MCP client (potentially an LLM acting on untrusted
# content, e.g. prompt injection from something else in the conversation).
# They're deliberately confined to this directory tree — no read or write
# outside it, no matter what path is requested — rather than trusting the
# caller. See README's MCP security note for the reasoning.
ALLOWED_ROOT = Path(__file__).resolve().parents[3]


class PathNotAllowedError(ValueError):
    """Raised when a caller-supplied path resolves outside ALLOWED_ROOT."""


def _resolve_within_allowed_root(path_str: str, *, purpose: str) -> Path:
    candidate = Path(path_str)
    resolved = candidate.resolve() if candidate.is_absolute() else (ALLOWED_ROOT / candidate).resolve()
    try:
        resolved.relative_to(ALLOWED_ROOT)
    except ValueError:
        raise PathNotAllowedError(
            f"{purpose} {path_str!r} resolves to {resolved}, which is outside the "
            f"allowed directory ({ALLOWED_ROOT}). Refusing rather than reading/writing "
            f"outside the project tree — use a path inside the project instead."
        ) from None
    return resolved

server = FastMCP(
    "sap-ocpm",
    instructions=(
        "Constructs object-centric process-mining event logs (OCEL 2.0) from raw SAP "
        "P2P tables, grounded in a curated 30-table knowledge base. Tools here NEVER "
        "invent a table, field, or join that isn't in the knowledge base — "
        "get_table_schema/find_join_path return found=false rather than guessing. "
        "Use search_tables/get_table_schema before referencing any table by name."
    ),
)


@server.tool()
def search_tables_tool(keywords: str = "", module: str = "") -> dict:
    """Search the grounded SAP P2P knowledge base by keyword and/or module."""
    result = search_tables(keywords, module or None)
    return result.model_dump()


@server.tool()
def get_table_schema_tool(table: str) -> dict:
    """Look up the full schema for one table name. found=false means it's not in the KB — don't invent it."""
    result = get_table_schema(table)
    return result.model_dump()


@server.tool()
def find_join_path_tool(table_a: str, table_b: str) -> dict:
    """Find the declared join path between two KB tables. found=false means no real join is declared."""
    result = find_join_path(table_a, table_b)
    return result.model_dump()


@server.tool()
def validate_sql_tool(query: str) -> dict:
    """Structurally validate a SQL query (syntax only)."""
    result = validate_sql(query)
    return result.model_dump()


@server.tool()
def check_event_log_spec_tool(spec_json: str) -> dict:
    """Structurally validate an OCEL-shaped event log spec given as a JSON string."""
    spec = json.loads(spec_json)
    result = check_event_log_spec(spec)
    return result.model_dump()


@server.tool()
def build_event_log(fixture_dir: str, granularity: str = "item", output_path: str = "") -> dict:
    """Runs the full constructor pipeline against a directory of raw SAP-table CSVs
    (matching the KB's schema, e.g. data/fixtures/bpi2019_sample/) and returns a
    summary: event/object counts, structural validation result, and every gap
    the constructor flagged rather than silently working around. granularity is
    "item" (default) or "order". If output_path is given, also writes the OCEL
    JSON there.

    Both paths are confined to the project directory tree (ALLOWED_ROOT) —
    a path resolving outside it is refused with a clear error rather than
    read from or written to."""
    try:
        resolved_fixture_dir = _resolve_within_allowed_root(fixture_dir, purpose="fixture_dir")
        resolved_output_path = (
            _resolve_within_allowed_root(output_path, purpose="output_path") if output_path else None
        )
    except PathNotAllowedError as exc:
        return {"error": str(exc)}

    tables = load_tables_from_fixture(resolved_fixture_dir)
    events, gaps = derive_activities(tables)
    gaps += flag_additional_gaps(events)

    cases = build_cases(events, granularity)
    spec = build_ocel(events, granularity=granularity)
    validation = validate_ocel(spec)

    if resolved_output_path:
        resolved_output_path.write_text(json.dumps(spec.model_dump(), indent=2))

    return {
        "granularity": granularity,
        "n_events_derived": len(events),
        "n_cases": len(cases),
        "n_ocel_objects": len(spec.objects),
        "n_ocel_events": len(spec.events),
        "object_types": spec.object_types,
        "event_types": spec.event_types,
        "ocel_validation": validation.model_dump(),
        "gaps": [{"category": g.category, "description": g.description, "ebeln": g.ebeln} for g in gaps],
        "output_written_to": str(resolved_output_path) if resolved_output_path else None,
    }


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
