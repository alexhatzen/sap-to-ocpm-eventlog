# sap-to-ocpm-eventlog

An agent that constructs **object-centric process-mining event logs (OCEL 2.0)**
from raw SAP tables — grounded in a curated table knowledge base, not model
recall. It's built for one audience in particular: someone who already knows
SAP, for whom the moment the agent invents a field or a join is the moment
the whole thing becomes worthless.

> **Status:** active prototype build. See [`BACKLOG.md`](BACKLOG.md) for what's
> done and what's next. This README describes the target design; sections
> below are marked ✅ done / 🚧 in progress / ⬜ not started.

## Why grounded retrieval, not model memory

The load-bearing decision in this project is that the agent never answers a
schema question from what an LLM "remembers" about SAP. Every table, field,
and join it can reference has to exist in a curated knowledge base that's
loaded and validated at startup — if a join points at a table or field that
isn't declared, the knowledge base refuses to load. That's what makes
`find_join_path` a graph search over real foreign keys instead of a guess,
and it's why a hallucinated table name is structurally impossible rather than
just unlikely.

## Scope: ~30 tables, Purchase-to-Pay, depth over breadth

The knowledge base currently covers **30 tables** in the **Purchase-to-Pay
(P2P)** process only — this is a deliberate scope decision, not an
oversight. A shallow knowledge base spanning ten SAP modules would be less
useful to a real consultant than a deep one covering the document flow a
P2P engagement actually touches: requisition → PO → goods receipt → invoice
verification → payment, plus the change-document and status-history tables
that let the agent reconstruct activities the header tables alone don't
timestamp.

Tables currently in the KB (`src/sap_ocpm/kb/tables/*.yaml`):

| Area | Tables |
|---|---|
| Purchase order header/item | `EKKO`, `EKPO`, `EKET`, `EKKN`, `EKAB` |
| PO history / 3-way match | `EKBE` |
| Purchase requisition | `EBAN`, `EBKN` |
| Goods movement | `MKPF`, `MSEG` |
| Invoice verification | `RBKP`, `RSEG` |
| Accounting / payment | `BKPF`, `BSEG` |
| Vendor master | `LFA1`, `LFB1`, `LFM1` |
| Material master | `MARA`, `MAKT`, `MARC` |
| Change documents | `CDHDR`, `CDPOS` |
| Status management | `JEST`, `JCDS`, `TJ02T` |
| Lookup/text tables | `T161T`, `T156T`, `T003T` |
| Output / pricing | `NAST`, `KONV` |

Each table entry carries its module, key fields, declared join keys
(cardinality included), the activities/processes it typically evidences,
known gotchas, and — critically for event log construction — which of its
date fields are date-only vs. paired with a real time field.

One deliberate modeling choice worth calling out: **CDHDR, JEST/JCDS, and
NAST use polymorphic keys** (`OBJECTID`, `OBJNR`, `OBJKY`) whose decoding
rule depends on the business object type. The KB does **not** model these as
clean declared joins — that would be exactly the kind of plausible-looking
fabrication this project exists to prevent. Instead each carries a `gotchas`
entry documenting the real decode rule, and `find_join_path` correctly
reports "no declared path" across them rather than guessing.

## Demo data: real, not fabricated

Rather than fabricate synthetic SAP data, the prototype grounds its demo in
the public **BPI Challenge 2019** purchase-order-handling event log —
251,734 cases / 1.6M events / 76,349 purchase documents from a real
SAP-based P2P process at a multinational coatings and paints company
(CC BY 4.0, [4TU.ResearchData, DOI 10.4121/uuid:d06aff4b-79f0-45e6-8ec8-e19730c248f1](https://data.4tu.nl/articles/dataset/BPI_Challenge_2019/12715853/1)).

> van Dongen, B.F. (2019). *BPI Challenge 2019*. Version 1. 4TU.ResearchData.

Since BPI2019 is already a flattened event log rather than raw SAP tables, a
shredding step reverse-engineers a sample of it back into a synthetic-but-grounded
raw table layer (`EKKO`/`EKPO`/`EKBE`/`CDHDR`/`CDPOS`/... shaped) using the
dataset's documented attributes. The original BPI2019 log for the sampled
purchase orders is kept alongside as **ground truth** — so the eval harness
can check the reconstructed event log against a real process, not just
against itself.

The checked-in fixture (`data/fixtures/bpi2019_sample/`, ~1.3MB, 300
real PO-item cases) is built by streaming the live 4TU.ResearchData
file and stopping as soon as enough traces are collected — the
downloader never pulls the full ~729MB XES file. The shredding rules
are documented per-activity in `src/sap_ocpm/dataprep/mapping.yaml`,
including the activities that don't have a clean standard-table home
(e.g. BPI2019's upstream "SRM: ..." sourcing-workflow steps) and are
honestly routed to a generic, disclosed proxy instead of an invented
table — the fixture's `mapping_coverage_report.json` shows exactly
which activities got an explicit mapping vs. the fallback on each run.

Running the constructor end-to-end against the real fixture (300 PO
items) recovers **15+ distinct activity types** (goods receipt, invoice
receipt, service entry sheets, invoice clearing, item creation, several
SRM sourcing steps, and more) from multiple raw sources — not the
three-activity, header-dates-only log naive attempts produce. It also
surfaces real, disclosed limits rather than guessing past them: events
on multi-item POs that CDHDR/CDPOS's proxy tables can't attribute to
one item are excluded from item-level cases (and correctly rolled up
at order level instead); `Clear Vendor Invoice` events, which BSEG
genuinely cannot tie back to a PO without decoding `BKPF.AWKEY`, are
related only to the `Vendor` object in the OCEL output, not fabricated
onto a `PurchaseOrder`. The output validates cleanly against this
project's own `check_event_log_spec` — the constructor holds itself to
the same structural bar the critic agent will use later.

## Architecture

| # | Component | Status |
|---|---|---|
| 1 | Grounded knowledge base (`src/sap_ocpm/kb/`) | ✅ done — 30 tables, loader with fail-fast join validation, 10 passing unit tests |
| 2 | Planner agent — decomposes use case → process scope, human review gate | ✅ done — Claude Agent SDK, live-verified end-to-end against the real KB |
| 3 | Deterministic tools — `search_tables`, `get_table_schema`, `find_join_path`, `validate_sql`, `check_event_log_spec` | ✅ done — 5 tools, 20 passing unit tests |
| 4 | Event log constructor — activity derivation, case granularity, timestamp resolution, gap flagging, OCEL writer | ✅ done — validated end-to-end against the real BPI2019 fixture, 12 new unit tests |
| 5 | Critic pass — validates the plan against the KB, flags gaps with confidence | ✅ done — Claude Agent SDK, live-verified end-to-end against a real planner-produced plan |
| 6 | Eval harness — expert-labeled use cases, table recall / precision / join validity / hallucination rate | ✅ done — harness built and CI-wired; only 2 **draft** cases so far, see below |
| 7 | Observability — per-run tool-call trace, token/cost accounting | ✅ done — cost taken directly from the SDK's own reported total, not a hand-maintained price list |
| 8 | Interfaces — MCP server + CLI | ✅ done — both live-verified end-to-end against the real fixture |

None of the deterministic tools (#3) ever call an LLM — that boundary is a
design commitment, not an implementation detail. Everything a hallucination
could hurt (schema lookup, joins, SQL validity, log-spec structure) is
handled by plain, testable Python. The LLM's job (#2 planner, #5 critic) is
scoped to decomposition, review, and flagging — never to inventing facts
about the schema.

Live-verified: the planner, run against a real 3-way-match use case, called
`search_tables`/`get_table_schema` before naming a single table, produced a
plan grounded entirely in real KB tables with honest medium-confidence notes
where it genuinely couldn't verify something (e.g. whether CDHDR logging is
actually active). The critic then independently re-verified every table and
join in that plan with its own tool calls — including confirming, correctly,
that CDHDR/CDPOS has no declared path to EKKO — and approved with two
substantive warnings rather than a blind rubber stamp.

## Eval harness

Every metric the design calls for is implemented in `eval/metrics.py`:
table recall, table-level precision (see honesty note below), join
validity rate, and hallucinated-table rate — **which is 0.0 in every
run so far, and is asserted as a CI failure condition if it's ever
not.** `eval/run_eval.py` runs in **cassette mode by default** — cached
planner outputs in `eval/cassettes/`, no API key or live call needed —
and only calls the live planner with `--live`.

Honesty note on scope: `ProcessPlan` tracks table-level selections, not
field-level ones, so this reports **table precision**, not the
"field precision" the original design named — extending the plan
schema to track field-level selections is a natural follow-up, not
done yet.

**Only 2 cases exist right now, both explicitly marked `is_draft: true`**
(`eval/cases/`). The load-bearing input — `expected_tables` per case —
needs real P2P domain expertise to be meaningful, and I'm not the
domain expert here: fabricating 15–25 "expert-labeled" cases myself
would undercut the exact premise of this project (no invented ground
truth). `run_eval.py` excludes drafts from the headline results by
default so a draft case's numbers can't be mistaken for a validated
benchmark. **Turning this into a real credential is one remaining step:
someone with real SAP P2P experience needs to write the other ~13-23
cases** — see `eval/cases/README.md`.

Generated results (cassette mode, drafts included since there's only
one non-draft-eligible cassette so far) live in `eval/RESULTS.md`,
regenerated by CI on every push.

## Observability

Every planner/critic run produces a `RunTrace` (`src/sap_ocpm/observability/`):
every tool call made, the SDK's own reported `total_cost_usd` and token
usage, turn count, and the raw result text — exported as both JSON and
readable markdown (`export_trace()`), with per-pipeline cost rollups via
`summarize_cost()`. Cost is read directly from the Claude Agent SDK's
`ResultMessage`, not recomputed against a hand-maintained price table
that would go stale the moment pricing changes.

## Interfaces

- **CLI** (`sap-ocpm`, Typer): `plan "<use case>"` (planner + review
  gate), `critic <plan.json>`, `build <fixture_dir>` (full constructor
  pipeline → OCEL JSON), `eval`, `mcp` (serve). Same core library
  underneath every command — no logic lives only in one interface.
- **MCP server** (`sap_ocpm.interfaces.mcp_server`, official `mcp`
  Python SDK / FastMCP — a different thing from the Claude Agent SDK's
  in-process tool server the planner/critic use internally): exposes
  the five deterministic tools plus a `build_event_log` orchestrator
  tool, live-verified end-to-end against the real fixture. Run it with
  `python3 -m sap_ocpm.interfaces.mcp_server` and point Claude
  Desktop/Cursor/any MCP client at it over stdio.

Full phase-by-phase build plan: [`BACKLOG.md`](BACKLOG.md).

## Repository layout

```
src/sap_ocpm/
  kb/            # grounded knowledge base (done)
  tools/         # deterministic tools (done)
  agents/        # planner + critic (Claude Agent SDK) (done)
  constructor/   # event log construction domain layer (done)
  dataprep/      # BPI2019 -> synthetic-but-grounded raw SAP tables (done)
  observability/ # trace + cost accounting (done)
  interfaces/    # MCP server + CLI (done)
eval/            # eval harness: cases, metrics, cassettes (done — see note on draft cases above)
data/            # BPI2019 fixture (checked-in sample) + raw (gitignored)
tests/           # unit + integration tests
```

## Running the tests

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install pydantic pyyaml networkx sqlglot requests typer rich mcp claude-agent-sdk pytest
PYTHONPATH=src:. python3 -m pytest tests/unit -q

# rebuild the checked-in BPI2019 fixture (streams live data, no local API key needed)
PYTHONPATH=src python3 -m sap_ocpm.dataprep.build_fixture 300
```

## Try it

```bash
# build an OCEL event log from the checked-in real-data fixture (no API key needed)
sap-ocpm build data/fixtures/bpi2019_sample --granularity item --output event_log.json

# run the eval harness (cassette mode, no API key needed)
sap-ocpm eval --include-drafts

# plan + review-gate a new use case (needs a logged-in `claude` CLI or ANTHROPIC_API_KEY)
sap-ocpm plan "analyze vendor payment timing against agreed payment terms"

# check that plan against the KB
sap-ocpm critic plan.json

# drop this project into Claude Desktop / Cursor / any MCP client
sap-ocpm mcp
```

## License

MIT for this project's own code. The BPI Challenge 2019 dataset used for
demo/eval data is CC BY 4.0 and separately attributed above; only a small
excerpt is checked into `data/fixtures/`.
