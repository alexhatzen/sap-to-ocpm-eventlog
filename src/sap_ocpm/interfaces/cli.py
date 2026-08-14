"""CLI — the scriptable/testable interface, wrapping the same core
library the MCP server and Python API use. No logic lives only here.

Commands: plan, critic, build, eval, mcp.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import typer

from sap_ocpm.agents.critic import run_critic
from sap_ocpm.agents.planner import render_plan, review_plan_interactive, run_planner
from sap_ocpm.agents.schemas import ProcessPlan
from sap_ocpm.constructor import (
    build_cases,
    build_ocel,
    derive_activities,
    flag_additional_gaps,
    load_tables_from_fixture,
    validate_ocel,
)

app = typer.Typer(help="Constructs OCEL 2.0 event logs from raw SAP P2P tables, grounded in a curated knowledge base.")


@app.command()
def plan(
    use_case: str = typer.Argument(..., help="Natural-language description of the process/analysis to plan for"),
    output: Path = typer.Option(Path("plan.json"), help="Where to save the approved plan"),
    interactive: bool = typer.Option(True, help="Run the accept/edit/reject review gate; --no-interactive auto-accepts"),
):
    """Run the planner agent and (by default) the human review gate before saving."""
    approved_plan, trace = asyncio.run(run_planner(use_case))
    typer.echo(f"(planner used {len(trace.tool_calls)} tool calls, cost ${trace.total_cost_usd or 0:.4f})\n")

    if interactive:
        result = review_plan_interactive(approved_plan)
        if result is None:
            typer.echo("Plan rejected — nothing saved.")
            raise typer.Exit(code=1)
        approved_plan = result
    else:
        typer.echo(render_plan(approved_plan))

    output.write_text(json.dumps(approved_plan.model_dump(), indent=2))
    typer.echo(f"\nSaved plan to {output}")


@app.command()
def critic(
    plan_file: Path = typer.Argument(..., help="A plan.json saved by `sap-ocpm plan`"),
):
    """Run the critic agent against a saved ProcessPlan."""
    loaded_plan = ProcessPlan.model_validate(json.loads(plan_file.read_text()))
    report, trace = asyncio.run(run_critic(loaded_plan))
    typer.echo(f"(critic used {len(trace.tool_calls)} tool calls, cost ${trace.total_cost_usd or 0:.4f})\n")

    from sap_ocpm.agents.critic import render_report

    typer.echo(render_report(report))
    if not report.approved:
        raise typer.Exit(code=1)


@app.command()
def build(
    fixture_dir: Path = typer.Argument(..., help="Directory of raw SAP-table CSVs (KB-shaped)"),
    granularity: str = typer.Option("item", help='"item" or "order"'),
    output: Path = typer.Option(Path("event_log.json"), help="Where to write the OCEL JSON"),
):
    """Run the constructor pipeline end-to-end against a directory of raw tables."""
    tables = load_tables_from_fixture(fixture_dir)
    events, gaps = derive_activities(tables)
    gaps += flag_additional_gaps(events)

    cases = build_cases(events, granularity)
    spec = build_ocel(events, granularity=granularity)
    validation = validate_ocel(spec)

    output.write_text(json.dumps(spec.model_dump(), indent=2))

    typer.echo(f"Derived {len(events)} events -> {len(cases)} cases ({granularity} granularity)")
    typer.echo(f"OCEL: {len(spec.objects)} objects, {len(spec.events)} events, types {spec.object_types}")
    typer.echo(f"Structurally valid: {validation.valid}" + ("" if validation.valid else f"  errors: {validation.errors}"))
    typer.echo(f"Gaps flagged: {len(gaps)}")
    for g in gaps[:10]:
        typer.echo(f"  - [{g.category}] {g.description[:120]}")
    if len(gaps) > 10:
        typer.echo(f"  ... and {len(gaps) - 10} more")
    typer.echo(f"\nWrote {output}")

    if not validation.valid:
        raise typer.Exit(code=1)


@app.command(name="eval")
def eval_(
    include_drafts: bool = typer.Option(False, "--include-drafts"),
    live: bool = typer.Option(False, "--live", help="Actually run the planner instead of using cassettes"),
):
    """Run the eval harness (see eval/run_eval.py)."""
    repo_root = Path(__file__).parents[3]
    sys.path.insert(0, str(repo_root))
    from eval.run_eval import render_results_table, run

    results, skipped = asyncio.run(run(include_drafts=include_drafts, live=live))
    typer.echo(render_results_table(results, skipped, include_drafts))


@app.command()
def mcp():
    """Start the MCP server (stdio transport) for use from Claude/Cursor/etc."""
    from sap_ocpm.interfaces.mcp_server import main as run_server

    run_server()


if __name__ == "__main__":
    app()
