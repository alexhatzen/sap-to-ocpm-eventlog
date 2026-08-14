"""activity_derivation — merges header creation dates, item-level
events, change documents, and status history into one activity stream.

Reads the raw SAP-table-shaped rows produced by dataprep (or a real
SAP export matching the same shape) and emits `ActivityEvent`s. Every
attribution decision that could plausibly be wrong is either resolved
via a real declared KB join (RSEG<->RBKP) or explicitly NOT resolved
and flagged as a gap (CDHDR/CDPOS item ambiguity on multi-item POs,
BSEG's real AWKEY limitation for PO attribution) — see
gap_flagging.py for what gets surfaced from here.
"""
from __future__ import annotations

import csv
from pathlib import Path

from sap_ocpm.constructor.schemas import ActivityEvent, Gap
from sap_ocpm.constructor.timestamp_resolution import resolve_timestamp

TABLE_FILES = [
    "ekko", "ekpo", "ekbe", "mkpf", "mseg", "rbkp", "rseg",
    "cdhdr", "cdpos", "lfa1", "bkpf", "bseg",
]


def load_tables_from_fixture(fixture_dir: Path | str) -> dict[str, list[dict]]:
    fixture_dir = Path(fixture_dir)
    tables: dict[str, list[dict]] = {}
    for name in TABLE_FILES:
        path = fixture_dir / f"{name}.csv"
        if not path.exists() or path.stat().st_size == 0:
            tables[name] = []
            continue
        with path.open(newline="") as f:
            tables[name] = list(csv.DictReader(f))
    return tables


def derive_activities(tables: dict[str, list[dict]]) -> tuple[list[ActivityEvent], list[Gap]]:
    gaps: list[Gap] = []
    events: list[ActivityEvent] = []
    seq = _Counter()

    items_per_ebeln: dict[str, set[str]] = {}
    for row in tables.get("ekpo", []):
        items_per_ebeln.setdefault(row["EBELN"], set()).add(row["EBELP"])

    # --- EKBE: goods receipt (VGABE=1) / invoice receipt (VGABE=2) ---
    mblnr_set = {row["MBLNR"] for row in tables.get("mkpf", [])}
    for row in tables.get("ekbe", []):
        ts = resolve_timestamp(row.get("CPUDT") or row.get("BUDAT", ""), row.get("CPUTM"))
        if row["VGABE"] == "1":
            activity = "Record Goods Receipt" if row.get("BELNR") in mblnr_set else "Record Service Entry Sheet"
        else:
            activity = "Record Invoice Receipt"
        events.append(ActivityEvent(
            ebeln=row["EBELN"], ebelp=row["EBELP"], activity=activity,
            timestamp=ts, source_table="EKBE", sequence=seq.next(),
        ))

    # --- RBKP joined to RSEG (the real declared join) for invoice creation ---
    rseg_by_belnr: dict[str, dict] = {}
    for row in tables.get("rseg", []):
        rseg_by_belnr[(row["BELNR"], row["GJAHR"])] = row
    for row in tables.get("rbkp", []):
        rseg = rseg_by_belnr.get((row["BELNR"], row["GJAHR"]))
        ts = resolve_timestamp(row.get("CPUDT", ""), row.get("CPUTM"))
        if rseg is None:
            gaps.append(Gap(
                category="unresolved_join",
                description=f"RBKP {row['BELNR']}/{row['GJAHR']} has no matching RSEG row — "
                            f"cannot attribute 'Vendor creates invoice' to a PO item.",
            ))
            continue
        events.append(ActivityEvent(
            ebeln=rseg["EBELN"], ebelp=rseg["EBELP"], activity="Vendor Creates Invoice",
            timestamp=ts, source_table="RBKP", sequence=seq.next(),
        ))

    # --- CDHDR/CDPOS: item creation, SRM proxy steps, generic fallback ---
    padded_to_real_ebeln = {ebeln.rjust(10, "0"): ebeln for ebeln in items_per_ebeln}
    cdhdr_by_changenr = {row["CHANGENR"]: row for row in tables.get("cdhdr", [])}
    for row in tables.get("cdpos", []):
        hdr = cdhdr_by_changenr.get(row["CHANGENR"])
        if hdr is None:
            continue
        ebeln = padded_to_real_ebeln.get(hdr["OBJECTID"])
        if ebeln is None:
            gaps.append(Gap(
                category="unresolved_objectid",
                description=f"CDHDR.OBJECTID {hdr['OBJECTID']!r} does not decode to any known EBELN "
                             f"under this KB's padding rule — event dropped rather than guessed.",
            ))
            continue

        ts = resolve_timestamp(hdr.get("UDATE", ""), hdr.get("UTIME"))
        user = hdr.get("USERNAME", "")

        if row["TABNAME"] == "EKPO" and row["FNAME"] == "EBELP" and row["CHNGIND"] == "I":
            events.append(ActivityEvent(
                ebeln=ebeln, ebelp=row["VALUE_NEW"], activity="Create Purchase Order Item",
                timestamp=ts, source_table="CDHDR", sequence=seq.next(), user=user,
            ))
            continue

        activity_name = row["VALUE_NEW"]
        item_set = items_per_ebeln.get(ebeln, set())
        if len(item_set) == 1:
            ebelp = next(iter(item_set))
            events.append(ActivityEvent(
                ebeln=ebeln, ebelp=ebelp, activity=activity_name,
                timestamp=ts, source_table="CDHDR", sequence=seq.next(), user=user,
            ))
        else:
            # ebelp=None marks this as header-only: case_granularity.py
            # excludes these from item-level cases (real ambiguity, not
            # guessed away) but includes them when rolling up to order level.
            events.append(ActivityEvent(
                ebeln=ebeln, ebelp=None, activity=activity_name,
                timestamp=ts, source_table="CDHDR", sequence=seq.next(), user=user,
            ))
            gaps.append(Gap(
                category="ambiguous_item_attribution",
                description=(
                    f"'{activity_name}' logged via CDHDR/CDPOS against PO {ebeln}, which has "
                    f"{len(item_set)} items — CDHDR/CDPOS carries no per-item field for this "
                    f"proxy event type, so it cannot be safely attributed to one item. Excluded "
                    f"from item-level cases, included when rolling up to order-level granularity "
                    f"(see mapping.yaml: SRM/unmapped-activity proxy)."
                ),
                ebeln=ebeln,
            ))

    # --- BSEG: clearing events, real SAP has no clean EBELN on this table ---
    for row in tables.get("bseg", []):
        ts = resolve_timestamp(row.get("AUGDT", ""))
        events.append(ActivityEvent(
            ebeln="", ebelp=None, activity="Clear Vendor Invoice",
            timestamp=ts, source_table="BSEG", sequence=seq.next(),
            extra={"vendor": row.get("LIFNR", "")},
        ))
    if tables.get("bseg"):
        gaps.append(Gap(
            category="known_limitation",
            description=(
                "BSEG/BKPF clearing events cannot be attributed to a specific purchase order "
                "item from standard fields alone — BSEG carries no EBELN, and tracing it back "
                "requires decoding BKPF.AWKEY, which this KB deliberately does not model as a "
                "clean join (see BKPF gotcha). 'Clear Vendor Invoice' events are related only "
                "to the Vendor object in the OCEL output, not to any PurchaseOrder/Item object."
            ),
        ))

    return events, gaps


class _Counter:
    def __init__(self):
        self._n = 0

    def next(self) -> int:
        self._n += 1
        return self._n
