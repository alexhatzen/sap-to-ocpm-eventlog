# BPI2019 sample fixture

300 purchase-order-item cases streamed directly from the public
BPI Challenge 2019 event log and shredded into SAP-table-shaped CSVs
per `../../../src/sap_ocpm/dataprep/mapping.yaml`.

Source: van Dongen, B.F. (2019). *BPI Challenge 2019*. Version 1.
4TU.ResearchData. CC BY 4.0.
DOI: 10.4121/uuid:d06aff4b-79f0-45e6-8ec8-e19730c248f1

- `ground_truth_log.csv` — the ORIGINAL, unshredded BPI2019 events for
  these cases (case_id, activity, timestamp, user, cumulative net
  worth). This is the eval harness's ground truth — what the
  constructor's reconstructed event log gets checked against.
- `{ekko,ekpo,ekbe,mkpf,mseg,rbkp,rseg,cdhdr,cdpos,lfa1,bkpf,bseg}.csv`
  — the synthetic-but-grounded raw SAP tables shredded from the same
  cases, matching the KB's 30-table schema.
- `mapping_coverage_report.json` — exactly which BPI2019 activities got
  an explicit per-table mapping vs. fell back to the generic
  CDHDR/CDPOS proxy for this run. Regenerate via:
  `PYTHONPATH=src python3 -m sap_ocpm.dataprep.build_fixture 300`

Every synthesized identifier (BELNR, MBLNR, CHANGENR, GJAHR) is
sequentially generated at shred time, not a real SAP number range —
see `mapping.yaml`'s `known_gaps` for the full list of disclosed
limitations.
