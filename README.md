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

## How the codebase fits together

Four layers, each only allowed to depend on the ones below it:

```
interfaces/    CLI (Typer) and MCP server (FastMCP) — thin, no logic of their own
agents/        planner + critic (Claude Agent SDK) — reason, never invent facts
tools/         search_tables, get_table_schema, find_join_path,     <- the two agents'
               validate_sql, check_event_log_spec — plain Python,      only window onto
               zero LLM calls, unit-tested in isolation                the knowledge base
constructor/   activity_derivation, case_granularity,
               timestamp_resolution, gap_flagging, ocel_writer — also plain Python
kb/            30 curated table YAMLs + the loader that validates them at import time
dataprep/      BPI2019 -> raw-table shredder (feeds constructor/ with real-shaped data)
observability/ RunTrace + cost accounting — wraps agents/, used by interfaces/
eval/          harness that scores agents/ output against kb/-grounded expected answers
```

**A full run, end to end** (`sap-ocpm plan` → `sap-ocpm critic` → `sap-ocpm build`):

1. `agents/planner.py` gets a natural-language use case. Its *only* tools
   are `tools/search_tables.py` and `tools/get_table_schema.py`
   (wrapped for the Claude Agent SDK in `agents/sdk_tools.py`), both of
   which just read `kb/tables/*.yaml` through `kb/loader.py`. It cannot
   name a table it hasn't looked up. Output: a `ProcessPlan`
   (`agents/schemas.py`), shown to you via `agents/planner.py`'s
   `review_plan_interactive()` — the human review gate — before
   anything else runs.
2. `agents/critic.py` gets that plan and re-derives its own opinion
   using `tools/get_table_schema.py` + `tools/find_join_path.py` — it
   does not trust the planner's claims, it re-checks them against the
   same KB. Output: a `CriticReport` with per-finding severity.
3. `sap-ocpm build <fixture_dir>` runs the actual construction, which
   never touches an LLM: `constructor/activity_derivation.py` reads raw
   SAP-table CSVs (from `dataprep/`'s BPI2019 shredder, or a real SAP
   export shaped the same way) and derives events from EKBE/RBKP+RSEG/
   CDHDR+CDPOS; `constructor/case_granularity.py` groups them into
   item- or order-level cases; `constructor/timestamp_resolution.py`
   gives every event a real, deterministically-ordered timestamp;
   `constructor/gap_flagging.py` (plus gaps raised inline during
   derivation) surfaces what couldn't be resolved instead of guessing;
   `constructor/ocel_writer.py` assembles the result and validates it
   with `tools/check_event_log_spec.py` — the same structural check the
   critic uses — before handing it back.
4. Every planner/critic call along the way is wrapped in a `RunTrace`
   (`observability/trace.py`) carrying every tool call plus the SDK's
   own reported cost, which `interfaces/cli.py` prints after each
   `plan`/`critic` invocation.
5. `eval/run_eval.py` exercises step 1 against hand-labeled
   `eval/cases/*.yaml` (via a cached `agents/planner.py` response in
   `eval/cassettes/` by default) and scores the result with
   `eval/metrics.py`, calling `tools/get_table_schema.py` and
   `tools/find_join_path.py` itself to check the plan's claims —
   exactly what the critic does, just turned into a number instead of
   a one-off report.

The dependency direction only ever points one way (`interfaces` →
`agents`/`constructor` → `tools`/`observability` → `kb`) — nothing in
`kb/` or `tools/` imports upward, which is what makes it possible to
unit-test the KB and the deterministic tools completely in isolation
from any agent or interface.

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

## Getting started

### 1. Set up the environment

```bash
git clone <this repo> && cd sap-to-ocpm-eventlog
python3 -m venv .venv && source .venv/bin/activate
pip install -e .          # editable install — this is what puts the `sap-ocpm` command on PATH
pip install pytest        # only needed to run the test suite, not a runtime dependency
```

`pip install -e .` pulls in everything declared in `pyproject.toml`
(`pydantic`, `pyyaml`, `networkx`, `sqlglot`, `requests`, `typer`,
`rich`, `mcp`, `claude-agent-sdk`, `pandas`) and registers the
`sap-ocpm` console script via its `[project.scripts]` entry point —
skip it and only `python3 -m sap_ocpm.interfaces.cli` will work, not
the bare `sap-ocpm` command used below.

### 2. Verify the install

```bash
PYTHONPATH=src:. python3 -m pytest tests/unit -q
# -> 86 passed
```

This runs entirely offline — no API key, no network call, no live
agent. It covers the knowledge base, all deterministic tools, the
BPI2019 shredder, the constructor, the MCP server, the CLI, and the
eval harness in cassette mode.

### 3. Try the parts that don't need an API key

The checked-in BPI2019 fixture (`data/fixtures/bpi2019_sample/`) makes
the constructor and eval harness runnable with zero setup beyond step 1:

```bash
# build a real OCEL 2.0 event log from real (BPI2019-derived) SAP tables
sap-ocpm build data/fixtures/bpi2019_sample --granularity item --output event_log.json
# -> "Derived 6964 events -> 300 cases (item granularity)"
# -> "Structurally valid: True"
# -> writes event_log.json

# run the eval harness against the one seeded cassette (cassette mode = no live call)
sap-ocpm eval --include-drafts
```

### 4. Enable the planner/critic agents (needs live access)

`plan` and `critic` call a real Claude Agent SDK agent, which needs
either:
- a logged-in `claude` CLI on PATH (`claude --version` to check — this
  is what the live testing during development actually used, no
  separate API key needed), **or**
- `ANTHROPIC_API_KEY` set in the environment.

```bash
sap-ocpm plan "analyze vendor payment timing against agreed payment terms"
# -> runs the planner, shows tool-call count + cost, then the accept/edit/reject review gate
# -> saves the approved plan to plan.json

sap-ocpm critic plan.json
# -> independently re-verifies every table/join in plan.json against the KB, prints a confidence-annotated report
```

`sap-ocpm eval --live` re-runs the planner for every case and refreshes
its cassette in `eval/cassettes/` — this is the only thing in the repo
that spends real tokens on every run; cassette mode (the default) never
does.

### 5. Run it as an MCP server (Claude Desktop / Cursor / any MCP client)

```bash
sap-ocpm mcp
# equivalently: python3 -m sap_ocpm.interfaces.mcp_server
```

Point an MCP client at this command over stdio. It exposes
`search_tables_tool`, `get_table_schema_tool`, `find_join_path_tool`,
`validate_sql_tool`, `check_event_log_spec_tool`, and
`build_event_log` (the full constructor pipeline as one call).

### 6. (Optional) rebuild the BPI2019 fixture from scratch

```bash
PYTHONPATH=src python3 -m sap_ocpm.dataprep.build_fixture 300
```

Streams live from 4TU.ResearchData and stops as soon as 300 traces are
collected — never downloads the full ~729MB file. Overwrites
`data/fixtures/bpi2019_sample/`.

### Where to go next

- [`BACKLOG.md`](BACKLOG.md) — full build log and what's genuinely still open.
- [`eval/cases/README.md`](eval/cases/README.md) — how to add a real,
  expert-labeled eval case (the biggest remaining gap).

## License

MIT for this project's own code. The BPI Challenge 2019 dataset used for
demo/eval data is CC BY 4.0 and separately attributed above; only a small
excerpt is checked into `data/fixtures/`.
