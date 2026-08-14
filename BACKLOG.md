# Backlog

Tracks build phases for the SAP → OCPM event log agent. Full design rationale
lives in `README.md`.

**All 11 phases from the original plan are now built and tested** (86 unit
tests passing, `PYTHONPATH=src:. python3 -m pytest tests/unit -q`). What's
genuinely still open, in priority order:

1. **The eval case set is the real remaining gap.** Only 2 cases exist, both
   `is_draft: true` (`eval/cases/`). The harness, metrics, cassette
   mechanism, and CI wiring are all done and tested — but the actual
   credential (evidence this thing works across a real spread of P2P use
   cases) doesn't exist until someone with real SAP P2P experience writes
   the other ~13-23 cases' `expected_tables`. See `eval/cases/README.md`.
2. Field-level precision isn't tracked (`ProcessPlan` only tracks table
   selections) — `eval/metrics.py` reports table-level precision instead,
   disclosed rather than mislabeled. Extending `ProcessPlan` to capture
   field-level selections would let this be closed properly.
3. No architecture diagram (the README's status table serves the same
   purpose in text form).
4. The eval harness's process-fidelity stretch metric (comparing a
   reconstructed OCEL log's activities/timing against BPI2019's real
   ground-truth log) isn't implemented — would need per-case ground-truth
   logs wired into the eval harness, not just `expected_tables`.

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

## Build log (in build order — all done, kept for detail/rationale)

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

### 5. Event log constructor (`src/sap_ocpm/constructor/`) — ✅ done
- [x] `activity_derivation.py` — reads the shredded raw tables and
      derives `ActivityEvent`s from EKBE (GR/service-entry via VGABE=1,
      discriminated by whether BELNR resolves to a real MKPF row vs.
      not; invoice receipt via VGABE=2), RBKP joined to RSEG (the real
      declared KB join) for invoice creation, and CDHDR/CDPOS for item
      creation + the SRM/unmapped-activity proxies. CDHDR's OBJECTID is
      decoded via the padding rule documented in the KB's own gotcha
      (build a padded->real EBELN map from known EKPO rows), not guessed.
- [x] `case_granularity.py` — item-level (`EBELN_EBELP`, default,
      matches BPI2019's native case notion) and order-level (`EBELN`)
      case construction. Header-only events (ambiguous CDHDR/CDPOS
      attribution on multi-item POs) are excluded from item-level cases
      and rolled up correctly at order level — verified this actually
      round-trips in the tests, not just documented as an intention.
- [x] `timestamp_resolution.py` — `resolve_timestamp()` combines SAP
      DATS+TIMS into ISO 8601, returns `None` (never a fabricated
      midnight) when unparseable; `sort_key()` gives a documented,
      deterministic tie-break (source-table priority, then insertion
      order) for events sharing an exact timestamp.
- [x] `gap_flagging.py` — flags undated events and the fixture's
      placeholder MENGE (BPI2019 has no item-level quantity), layered on
      top of the gaps `activity_derivation` already surfaces
      (unresolved RSEG join, undecodable CDHDR OBJECTID, ambiguous
      multi-item attribution, BSEG's real AWKEY limitation).
- [x] `ocel_writer.py` — `build_ocel()` emits an OCEL-2.0-shaped
      `EventLogSpec` (PurchaseOrder/PurchaseOrderItem/Vendor object
      types); vendor-only events (BSEG clearing) relate only to the
      `Vendor` object rather than a fabricated PO link. Validates its
      own output through `check_event_log_spec` before returning — same
      bar the critic agent will apply later, not a looser one.
- [x] Validated end-to-end against the real 300-case BPI2019 fixture:
      6,964 events derived, 15+ distinct activity types recovered
      (vs. a naive header-dates-only 3-activity log), item-level case
      count matches EKPO row count exactly (300), order-level matches
      EKKO (198), OCEL output validates with zero structural errors.
      Found and correctly preserved (not "fixed") a real BPI2019 data
      quality quirk — a duplicate "Vendor creates debit memo" event
      timestamped 2001 instead of 2018 — confirming the pipeline isn't
      silently cleaning the ground truth it's supposed to be checked
      against later.
- [x] 12 new unit tests (52 total): timestamp edge cases, single- vs
      multi-item attribution, the BSEG/AWKEY limitation, undated-event
      flagging, OCEL vendor-only relations, and a full run against the
      real fixture.

### 6. Planner agent (`src/sap_ocpm/agents/planner.py`) — ✅ done
- [x] `agents/sdk_tools.py` wraps the deterministic tools as Claude Agent
      SDK in-process MCP tools (`@sdk.tool`), scoped per agent:
      `PLANNER_TOOLS` = search_tables + get_table_schema only;
      `CRITIC_TOOLS` = get_table_schema + find_join_path +
      check_event_log_spec. Confirmed live that the SDK's actual tool
      name is `mcp__<server>__<tool>` before writing the real agents.
- [x] `run_planner()`: Claude Agent SDK agent (`claude_agent_sdk.query`),
      system prompt hard-requires a tool call before naming any table,
      output parsed as a fenced ```json block into `ProcessPlan` — raises
      `PlannerError` rather than silently returning a fabricated plan on
      malformed output.
- [x] `ProcessPlan`/`ActivityMapping`/`ConfidenceNote`/`PlanGap` pydantic
      schemas (`agents/schemas.py`).
- [x] `review_plan_interactive()` — CLI review gate: prints the plan,
      accept/edit(drops into `$EDITOR` on a JSON scratch file)/reject.
      Real interrupt, not cosmetic — full CLI wiring is backlog item 10.
- [x] **Live-verified end-to-end** against the real KB (no API key was
      configured as an env var; the SDK used the already-authenticated
      `claude` CLI's own session) with a real 3-way-match use case: the
      planner called `search_tables`/`get_table_schema` 16 times before
      naming a single table, referenced only 9 real KB tables, and
      produced honest medium-confidence notes on things it genuinely
      couldn't verify (e.g. whether CDHDR logging is active for
      EINKBELEG in a given system). This was a manual smoke-test run,
      not saved as a fixture — see the README's live-verified callout.

### 7. Critic agent (`src/sap_ocpm/agents/critic.py`) — ✅ done
- [x] `run_critic()`: Claude Agent SDK agent, tools limited to
      `get_table_schema`, `find_join_path` (`check_event_log_spec` also
      wrapped and available). System prompt requires it to re-verify
      every table/join with its own tool calls rather than trusting the
      planner's claims.
- [x] `CriticReport`/`CriticFinding` pydantic schemas.
- [x] `render_report()` for a readable confidence-annotated gap report.
- [x] **Live-verified end-to-end** against the real planner output above:
      independently re-checked all 9 tables (`get_table_schema`) and 12
      join pairs (`find_join_path`), correctly confirmed CDHDR/CDPOS has
      no declared path to EKKO/EKPO (matching the KB's deliberate design,
      not treated as an automatic failure), caught that one activity's
      `source_tables` list omitted an intermediary table its own join
      path required, and approved with two substantive warnings — not a
      blind rubber stamp.

### 8. Eval harness (`eval/`) — ✅ harness done, case set NOT done
- [x] `eval/schema.py` — `EvalCase` (id, use_case, expected_tables, `is_draft`).
- [x] `eval/cases/*.yaml` — **only 2 cases exist, both `is_draft: true`**.
      Real expert labels (15–25 cases) still needed — see
      `eval/cases/README.md`. Did not fabricate "expert-labeled" cases;
      that would undercut the project's own premise.
- [x] `eval/metrics.py` — table recall, **table** precision (not field —
      `ProcessPlan` doesn't track field-level selections, disclosed as a
      scope note rather than silently relabeled), hallucinated-table
      rate (0.0 in every run so far, asserted in CI), join validity
      rate. BPI2019 process-fidelity stretch metrics (activity-set
      recall / case-count agreement vs. the real log) not implemented —
      would need per-case ground-truth logs, not just expected tables.
- [x] `eval/cassettes/` — one real cassette
      (`3way_match_item_level.json`), seeded from an actual live planner
      run, not synthesized.
- [x] `run_eval.py` (cassette-mode default, `--live` to refresh
      cassettes) + `.github/workflows/eval.yml` — CI runs unit tests,
      runs the harness, and hard-fails if `hallucinated_table_rate != 0`.
      (README-staleness check from the original plan not implemented —
      `eval/RESULTS.md` is regenerated by CI instead of a README table,
      simpler and avoids partial-file-diff churn.)

### 9. Observability (`src/sap_ocpm/observability/`) — ✅ done
- [x] `trace.py` — `RunTrace`/`ToolCallRecord`, JSON + markdown export
      (`export_trace()`), timestamped filenames so runs don't clobber.
- [x] `cost.py` — `summarize_cost()` aggregates across runs. **Design
      change from the original plan:** cost is read directly from the
      Claude Agent SDK's own `ResultMessage.total_cost_usd`/`usage`
      (confirmed via reflection these fields exist), not computed
      against a hand-maintained `pricing.yaml` — the SDK already knows
      the real, current cost of the run it just made; a static price
      list would just go stale.
- [x] Wired into `planner.py`/`critic.py` (both now return `RunTrace`
      instead of a raw tool-call list) and the CLI (`plan`/`critic`
      commands print tool-call count + cost). Not separately wired into
      MCP tool response metadata — `build_event_log` doesn't invoke an
      agent, so there's no per-call agent cost to surface there.
- [x] 8 new offline unit tests.

### 10. Interfaces (`src/sap_ocpm/interfaces/`) — ✅ done
- [x] `mcp_server.py` — official `mcp` Python SDK (`FastMCP`, distinct
      from `claude_agent_sdk`'s in-process tool server used internally
      by the planner/critic). Exposes the 5 deterministic tools plus
      `build_event_log`. Live-verified: tool registration, a schema
      lookup, and a full `build_event_log` run against the real fixture
      all execute correctly end-to-end.
- [x] `cli.py` — Typer: `plan`, `critic`, `build`, `eval`, `mcp`. `build`
      and `eval` verified via `CliRunner` against the real fixture and
      real cassette; `plan`/`critic`/`mcp` verified manually (need a
      live agent run / blocking stdio server, same pattern as the rest
      of this project's live-agent-touching code).
- [x] 7 new offline unit tests for the MCP server, 4 for the CLI.
- [x] End-to-end demo commands documented in README's "Try it" section
      instead of a separate demo script — the CLI itself *is* the demo.
- [x] **Security hardening (post-launch):** `build_event_log`'s
      `fixture_dir`/`output_path` params originally accepted any path —
      caught during a user security review after wiring this into Claude
      Desktop. Added `ALLOWED_ROOT` + `_resolve_within_allowed_root()`
      confining both to the project directory tree; anything resolving
      outside it (absolute paths, `../` traversal) is refused with a
      clear error instead of read/written. Live-verified against
      `/etc` and `/tmp/pwned.json` — both rejected, nothing written.
      Deliberately scoped to the MCP tool only, not the CLI's `build`
      command (that's a path the user gives themselves at their own
      terminal — different trust boundary than a path an MCP client,
      potentially driven by untrusted conversation content, supplies).
      4 new tests in `tests/unit/test_mcp_server.py`.

### 11. README pass — ✅ done
- [x] Explicit "~30 tables, P2P scope, depth over breadth" statement.
- [x] BPI2019 citation + license note.
- [x] Eval harness section with an honest note on the 2-draft-case
      status and the table-vs-field-precision scope decision.
- [x] "Try it" section with real, copy-pasteable CLI commands.
- [ ] Architecture diagram — not done; the architecture status table
      serves the same purpose in text form for now.

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
