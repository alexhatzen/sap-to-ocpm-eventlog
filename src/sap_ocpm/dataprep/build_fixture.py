"""Builds the checked-in BPI2019 sample fixture under
data/fixtures/bpi2019_sample/: streams N real traces, shreds them into
SAP-table-shaped CSVs, and writes the original (unshredded) log
alongside as ground truth, plus a mapping-coverage report so it's
obvious at a glance which activities got a real per-table mapping and
which fell back to the generic proxy.

Usage: PYTHONPATH=src python3 -m sap_ocpm.dataprep.build_fixture [N]
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from sap_ocpm.dataprep.download_bpi2019 import stream_bpi2019_traces
from sap_ocpm.dataprep.shred_to_sap_tables import ShreddedTables, shred_traces

FIXTURE_DIR = Path(__file__).parents[3] / "data" / "fixtures" / "bpi2019_sample"

TABLE_ATTR_NAMES = [
    "ekko", "ekpo", "ekbe", "mkpf", "mseg", "rbkp", "rseg",
    "cdhdr", "cdpos", "lfa1", "bkpf", "bseg", "ground_truth_log",
]


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("")
        return
    fieldnames = list({k for row in rows for k in row})
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_fixture(n_traces: int = 300) -> ShreddedTables:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    traces = list(stream_bpi2019_traces(max_traces=n_traces))
    result = shred_traces(traces)

    for attr in TABLE_ATTR_NAMES:
        _write_csv(FIXTURE_DIR / f"{attr}.csv", getattr(result, attr))

    (FIXTURE_DIR / "mapping_coverage_report.json").write_text(
        json.dumps(dict(sorted(result.mapping_coverage.items(), key=lambda kv: -kv[1])), indent=2)
    )

    provenance = f"""# BPI2019 sample fixture

{n_traces} purchase-order-item cases streamed directly from the public
BPI Challenge 2019 event log and shredded into SAP-table-shaped CSVs
per `../../../src/sap_ocpm/dataprep/mapping.yaml`.

Source: van Dongen, B.F. (2019). *BPI Challenge 2019*. Version 1.
4TU.ResearchData. CC BY 4.0.
DOI: 10.4121/uuid:d06aff4b-79f0-45e6-8ec8-e19730c248f1

- `ground_truth_log.csv` — the ORIGINAL, unshredded BPI2019 events for
  these cases (case_id, activity, timestamp, user, cumulative net
  worth). This is the eval harness's ground truth — what the
  constructor's reconstructed event log gets checked against.
- `{{ekko,ekpo,ekbe,mkpf,mseg,rbkp,rseg,cdhdr,cdpos,lfa1,bkpf,bseg}}.csv`
  — the synthetic-but-grounded raw SAP tables shredded from the same
  cases, matching the KB's 30-table schema.
- `mapping_coverage_report.json` — exactly which BPI2019 activities got
  an explicit per-table mapping vs. fell back to the generic
  CDHDR/CDPOS proxy for this run. Regenerate via:
  `PYTHONPATH=src python3 -m sap_ocpm.dataprep.build_fixture {n_traces}`

Every synthesized identifier (BELNR, MBLNR, CHANGENR, GJAHR) is
sequentially generated at shred time, not a real SAP number range —
see `mapping.yaml`'s `known_gaps` for the full list of disclosed
limitations.
"""
    (FIXTURE_DIR / "README.md").write_text(provenance)

    return result


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    result = build_fixture(n)
    print(f"Wrote fixture for {n} traces to {FIXTURE_DIR}")
    for attr in TABLE_ATTR_NAMES:
        print(f"  {attr}: {len(getattr(result, attr))} rows")
