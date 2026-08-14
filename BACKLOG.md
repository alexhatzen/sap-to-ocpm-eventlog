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

### 4. Data prep (`src/sap_ocpm/dataprep/`) — ✅ done
- [x] `download_bpi2019.py` — no CSV export actually exists for this
      dataset (verified against the figshare API backing 4TU.ResearchData,
      article 12715853: only the ~729MB XES file is hosted). Built a
      streaming SAX-based downloader instead — `stream_bpi2019_traces()`
      reads the live file over HTTP and stops as soon as N traces are
      collected, closing the connection early. Never downloads the full
      file. Verified against the real URL (5-trace and 300-trace runs).
- [x] `mapping.yaml` — documented BPI2019-attribute → SAP-field mapping,
      grounded in the actual observed XES structure (fetched a byte-range
      sample first rather than guessing). Explicit per-activity table
      routing for the high-frequency activities (`Create Purchase Order
      Item`, `Vendor creates invoice`, `Record Goods Receipt`, `Record
      Invoice Receipt`, `Record Service Entry Sheet`, `Clear Invoice`,
      `SRM: *`), a documented generic CDHDR/CDPOS fallback for everything
      else, and a `known_gaps` section (no MATNR/quantity in BPI2019, so
      MARA/MAKT/MARC are out of scope; synthesized IDs aren't real SAP
      number ranges).
- [x] `shred_to_sap_tables.py` — applies the mapping; `shred_traces()`
      returns a `ShreddedTables` dataclass (rows per KB table) plus a
      `mapping_coverage` counter — every shredder run reports exactly
      which activities got an explicit mapping vs. the fallback, rather
      than silently dropping or inventing coverage.
- [x] `build_fixture.py` — streams a fixed sample, shreds it, writes CSVs
      + `mapping_coverage_report.json` + a provenance `README.md` to
      `data/fixtures/bpi2019_sample/`.
- [x] Checked-in fixture: `data/fixtures/bpi2019_sample/` — 300 real
      PO-item cases (~1.3MB total across 13 CSVs), CC BY 4.0, cited
      inline. The original (unshredded) BPI2019 events for the same
      cases are kept as `ground_truth_log.csv` — the eval harness's
      ground truth.
- [x] Unit tests (`tests/unit/test_shred_to_sap_tables.py`, 10 passing,
      offline/no network) covering every mapped activity branch, the
      SRM proxy, the generic fallback, EKKO dedup across items on the
      same PO, and ground-truth-log fidelity.

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
