# Eval cases

Each `*.yaml` in this directory is one `EvalCase` (see `../schema.py`).
The load-bearing field is `expected_tables` — "which tables would a
consultant with real SAP P2P experience actually pick for this use
case." That has to come from real domain expertise, not a plausible
guess, or the eval harness measures nothing.

**Current status: 2 draft cases only**, `is_draft: true`, seeded by me
(the agent building this project) as structurally-correct placeholders
so the harness itself is exercised and testable. They are NOT a
substitute for the 15–25 expert-labeled cases the design calls for —
fabricating "expert-labeled" cases myself would undercut the exact
premise of this project (no invented ground truth). `run_eval.py`
excludes draft cases from the headline results table by default
(`--include-drafts` to see them anyway) so a draft case's numbers can't
be mistaken for a validated result.

**To add a real case:** copy the shape of an existing YAML, set
`is_draft: false` once you've actually reviewed `expected_tables`
yourself, and drop the case's cassette (if run live) into `../cassettes/`.
