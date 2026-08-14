"""Unit tests for the CLI's offline commands (build, eval, --help).

`plan`/`critic`/`mcp` need a live agent run or a blocking stdio server
and are verified manually, same pattern as the rest of this project's
live-agent-touching code.
"""
from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from sap_ocpm.interfaces.cli import app

runner = CliRunner()
FIXTURE_DIR = Path(__file__).parents[2] / "data" / "fixtures" / "bpi2019_sample"


def test_help_exits_zero():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "plan" in result.output and "build" in result.output and "eval" in result.output


def test_build_against_real_fixture(tmp_path):
    out = tmp_path / "log.json"
    result = runner.invoke(app, ["build", str(FIXTURE_DIR), "--granularity", "item", "--output", str(out)])
    assert result.exit_code == 0, result.output
    assert "Structurally valid: True" in result.output
    assert out.exists()
    data = json.loads(out.read_text())
    assert "PurchaseOrderItem" in data["object_types"]


def test_build_order_granularity_has_no_item_objects(tmp_path):
    out = tmp_path / "log.json"
    result = runner.invoke(app, ["build", str(FIXTURE_DIR), "--granularity", "order", "--output", str(out)])
    assert result.exit_code == 0
    data = json.loads(out.read_text())
    assert "PurchaseOrderItem" not in data["object_types"]


def test_eval_command_runs_in_cassette_mode():
    result = runner.invoke(app, ["eval", "--include-drafts"])
    assert result.exit_code == 0, result.output
    assert "3way_match_item_level" in result.output
    assert "hallucinated table rate 0.000" in result.output
