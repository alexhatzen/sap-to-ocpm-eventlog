# Backlog

Tracks remaining build phases for the SAP → OCPM event log agent. Full design
rationale lives in the plan this backlog was generated from (grounded KB,
deterministic tools, planner/critic split, BPI2019-grounded data, OCEL 2.0
output — see `README.md` once written, or the original planning conversation).

## Done

- [x] **Repo scaffold** — `pyproject.toml`, `src/sap_ocpm` package layout,
      `.gitignore`, directory structure for `eval/`, `data/`, `tests/`.
- [x] **Knowledge base** (`src/sap_ocpm/kb/`) — pydantic schema
      (`schema.py`: `TableSpec`/`FieldSpec`/`JoinEdge`/`TimestampFieldSpec`),
      fail-fast loader with join-graph validation (`loader.py`), and 30
      curated P2P table YAMLs under `kb/tables/` (EKKO, EKPO, EKBE, EKKN,
      EBAN, EBKN, EKET, EKAB, RSEG, RBKP, BSEG, BKPF, LFA1, LFB1, LFM1,
      MARA, MAKT, MARC, MSEG, MKPF, CDHDR, CDPOS, JEST, JCDS, TJ02T,
      T161T, T156T, T003T, NAST, KONV). Unit tests in
      `tests/unit/test_kb_loader.py` (10 passing) cover: real-KB load,
      join-target existence, the deliberate absence of clean joins on
      polymorphic keys (CDHDR/JEST/NAST), and rejection of dangling
      joins / bad filenames / empty KB dirs.
- Verified locally: `PYTHONPATH=src python3 -m pytest tests/unit -q` → 10 passed.
  Venv at `.venv/` (not committed) has `pydantic`, `pyyaml`, `networkx`,
  `sqlglot`, `pytest` installed.

## Next up (in build order)

### 3. Deterministic tools (`src/sap_ocpm/tools/`) — ✅ done
- [x] `search_tables.py` — keyword/module search over the KB (plain
      substring/keyword match, cached KB load via `tools/_shared.py`).
- [x] `get_table_schema.py` — KB lookup, explicit `found=False` + error
      message (not a silent `None`) for undeclared tables.
- [x] `find_join_path.py` — `networkx` `MultiGraph` over every table's
      `join_keys` edges, shortest-path between two tables, returns the
      literal join chain (field-level, cardinality included) or an
      explicit "no declared path" result. Verified CDHDR→EKKO correctly
      returns no path instead of guessing across the polymorphic key.
- [x] `validate_sql.py` — `sqlglot` parse + statement-type check.
      Two things learned building this, documented in the module
      docstring: sqlglot has no native SAP HANA dialect (default is
      generic/ANSI, not a fabricated "hana"), and `sqlglot.parse()` is
      permissive enough to silently reinterpret a typo'd keyword
      ("SELEKT * FRM EKKO") as a legal arithmetic expression instead of
      raising — caught by additionally requiring the parsed result be a
      real `exp.Query`/`DDL`/`DML` statement.
- [x] `check_event_log_spec.py` — structural validation of an OCEL-shaped
      spec (own minimal `EventLogSpec`/`OcelObject`/`OcelEvent` pydantic
      models pending the real constructor): declared object/event types,
      ISO-8601 timestamps, no dangling object references, duplicate-id
      detection, zero-event warning.
- [x] Unit tests (`tests/unit/test_tools.py`, 20 passing): hallucinated
      table canary, case-insensitivity, known join chains, no-path for
      CDHDR, malformed SQL, dangling event-log references, bad
      timestamps, typed vs dict input.

### 4. Data prep (`src/sap_ocpm/dataprep/`)
- [ ] `download_bpi2019.py` — pull the ~38MB CSV export from
      4TU.ResearchData (DOI `10.4121/uuid:d06aff4b-79f0-45e6-8ec8-e19730c248f1`),
      cache under `data/raw/` (gitignored).
- [ ] `mapping.yaml` — documented BPI2019-attribute → SAP-field mapping
      (`Purchasing Document`→EKKO/EKPO.EBELN, `Item`→EKPO.EBELP,
      `Vendor`→LFA1.LIFNR, `GR-Based Inv. Verif.`→EKPO.WEBRE,
      `Item Category`→EKPO.PSTYP, event→CDHDR/CDPOS/EKBE row depending on
      activity type).
- [ ] `shred_to_sap_tables.py` — apply the mapping, produce raw-table CSVs
      matching the 30-table KB schema.
- [ ] Checked-in fixture: `data/fixtures/bpi2019_sample/` — stratified
      few-hundred-PO excerpt (CC BY 4.0, cite
      `van Dongen, B.F. (2019). BPI Challenge 2019. 4TU.ResearchData.`).
      Retain the *original* BPI2019 log for the same sampled POs
      alongside the shredded tables — it's the eval harness's ground truth.

### 5. Event log constructor (`src/sap_ocpm/constructor/`)
- [ ] `activity_derivation.py` — merge header dates, item events,
      CDHDR/CDPOS, JEST/JCDS into one activity stream.
- [ ] `case_granularity.py` — order-level vs item-level case-ID
      construction, explicit tradeoffs.
- [ ] `timestamp_resolution.py` — documented tie-break/ordering rules for
      date-only vs date+time fields (every table's `timestamp_fields`
      entry in the KB already flags which is which — use it).
- [ ] `gap_flagging.py` — flag requested-but-unavailable data instead of
      fabricating it.
- [ ] `ocel_writer.py` — emit OCEL 2.0 JSON (PurchaseOrder,
      PurchaseOrderItem, Vendor, Material, Invoice object types +
      relations); optional flat-XES export.
- [ ] Validate by hand against the known BPI2019 process shape once the
      fixture exists.

### 6. Planner agent (`src/sap_ocpm/agents/planner.py`)
- [ ] Claude Agent SDK agent, tools limited to `search_tables` +
      `get_table_schema` (read-only KB retrieval only).
- [ ] `ProcessPlan` pydantic schema (`agents/schemas.py`).
- [ ] CLI review-gate: print plan → accept/edit/reject before anything
      downstream runs.

### 7. Critic agent (`src/sap_ocpm/agents/critic.py`)
- [ ] Claude Agent SDK agent, tools limited to `get_table_schema`,
      `find_join_path`, `check_event_log_spec` (read-only + validation,
      no fix-it powers).
- [ ] Confidence-annotated gap report as part of the run artifact.

### 8. Eval harness (`eval/`)
- [ ] `eval/cases/*.yaml` — 15–25 use cases. **Needs the user's own
      expert labels** — do not fabricate "expert-labeled" ground truth;
      scaffold the schema + a couple of clearly-marked draft examples
      only, and flag the rest as an explicit open task for the user.
- [ ] `eval/metrics.py` — table recall, field precision, join validity
      rate, hallucinated-table rate (must be zero), plus the BPI2019
      stretch metrics (activity-set recall, case-count/timestamp
      agreement vs the real log).
- [ ] `eval/cassettes/` — recorded LLM responses so CI doesn't need a
      live API key.
- [ ] `run_eval.py` + `.github/workflows/eval.yml` — CI fails if
      hallucinated-table rate ≠ 0 or README results table is stale.

### 9. Observability (`src/sap_ocpm/observability/`)
- [ ] `trace.py` — per-run tool-call/decision trace, readable JSON/markdown export.
- [ ] `cost.py` — token/cost accounting against an editable `pricing.yaml`.
- [ ] Wire into CLI (`--trace`, `--show-cost`) and MCP tool response metadata.

### 10. Interfaces (`src/sap_ocpm/interfaces/`)
- [ ] `mcp_server.py` — official `mcp` Python SDK, expose the 5
      deterministic tools + a `build_event_log` orchestrator tool.
- [ ] `cli.py` — Typer: `sap-ocpm plan`, `sap-ocpm build`, `sap-ocpm eval`,
      `sap-ocpm mcp`.
- [ ] End-to-end demo script.

### 11. README pass
- [ ] Explicit "~30 tables, P2P scope, depth over breadth" statement.
- [ ] BPI2019 citation + license note.
- [ ] Eval results table (generated, not hand-typed).
- [ ] Architecture diagram.

## Environment notes for resuming

- Local venv: `.venv/` (gitignored) — `python3 -m venv .venv && source .venv/bin/activate`,
  then `pip install -e .[dev]` once `pyproject.toml`'s deps are all needed,
  or install incrementally (`pydantic pyyaml networkx sqlglot typer rich
  pandas mcp claude-agent-sdk pytest` as phases need them).
- Run KB tests: `PYTHONPATH=src python3 -m pytest tests/unit -q`.
- Claude Agent SDK phases (planner/critic) will need `ANTHROPIC_API_KEY`
  set — not required for anything done so far.
- BPI2019 download requires outbound network access to 4TU.ResearchData —
  not attempted yet.
