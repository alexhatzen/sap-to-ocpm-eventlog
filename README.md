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
against itself. *(⬜ not yet built — see Backlog.)*

## Architecture

| # | Component | Status |
|---|---|---|
| 1 | Grounded knowledge base (`src/sap_ocpm/kb/`) | ✅ done — 30 tables, loader with fail-fast join validation, 10 passing unit tests |
| 2 | Planner agent — decomposes use case → process scope, human review gate | ⬜ not started |
| 3 | Deterministic tools — `search_tables`, `get_table_schema`, `find_join_path`, `validate_sql`, `check_event_log_spec` | ✅ done — 5 tools, 20 passing unit tests |
| 4 | Event log constructor — activity derivation, case granularity, timestamp resolution, gap flagging, OCEL writer | ⬜ not started |
| 5 | Critic pass — validates the plan against the KB, flags gaps with confidence | ⬜ not started |
| 6 | Eval harness — 15–25 expert-labeled use cases, table recall / field precision / join validity / hallucination rate | ⬜ not started |
| 7 | Observability — per-run tool-call trace, token/cost accounting | ⬜ not started |
| 8 | Interfaces — MCP server + CLI | ⬜ not started |

None of the deterministic tools (#3) ever call an LLM — that boundary is a
design commitment, not an implementation detail. Everything a hallucination
could hurt (schema lookup, joins, SQL validity, log-spec structure) is
handled by plain, testable Python. The LLM's job (#2 planner, #5 critic) is
scoped to decomposition, review, and flagging — never to inventing facts
about the schema.

Full phase-by-phase build plan: [`BACKLOG.md`](BACKLOG.md).

## Repository layout

```
src/sap_ocpm/
  kb/            # grounded knowledge base (done)
  tools/         # deterministic tools (done)
  agents/        # planner + critic (Claude Agent SDK)
  constructor/   # event log construction domain layer
  dataprep/      # BPI2019 -> synthetic-but-grounded raw SAP tables
  observability/ # trace + cost accounting
  interfaces/    # MCP server + CLI
eval/            # eval harness: cases, metrics, cassettes
data/            # BPI2019 fixture (checked-in sample) + raw (gitignored)
tests/           # unit + integration tests
```

## Running the tests

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install pydantic pyyaml networkx sqlglot pytest
PYTHONPATH=src python3 -m pytest tests/unit -q
```

## License

MIT for this project's own code. The BPI Challenge 2019 dataset used for
demo/eval data is CC BY 4.0 and separately attributed above; only a small
excerpt is checked into `data/fixtures/`.
