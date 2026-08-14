"""Shreds streamed BPI2019 traces into raw, SAP-table-shaped rows per
`mapping.yaml`.

The original (unshredded) BPI2019 events are also returned unchanged,
per case — that's the eval harness's ground truth. Every row this
module produces is honestly synthetic where the mapping says so (see
`mapping.yaml`'s `known_gaps`); nothing here should be mistaken for a
real SAP export.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from itertools import count

from sap_ocpm.dataprep.download_bpi2019 import Bpi2019Trace

_OBJECTCLAS_PO = "EINKBELEG"

# Freeform BPI2019 "Item Category" text -> a short synthetic PSTYP-style code.
# Real SAP PSTYP values are 0 (standard)/3 (consignment)/etc; these text
# categories don't correspond 1:1 to real client config, so codes here are
# arbitrary but stable, and documented as such in mapping.yaml.
_ITEM_CATEGORY_TO_PSTYP = {
    "3-way match, invoice before gr": "0",
    "3-way match, invoice after gr": "0",
    "2-way match": "0",
    "consignment": "3",
}


@dataclass
class ShreddedTables:
    ekko: list[dict] = field(default_factory=list)
    ekpo: list[dict] = field(default_factory=list)
    ekbe: list[dict] = field(default_factory=list)
    mkpf: list[dict] = field(default_factory=list)
    mseg: list[dict] = field(default_factory=list)
    rbkp: list[dict] = field(default_factory=list)
    rseg: list[dict] = field(default_factory=list)
    cdhdr: list[dict] = field(default_factory=list)
    cdpos: list[dict] = field(default_factory=list)
    lfa1: list[dict] = field(default_factory=list)
    bkpf: list[dict] = field(default_factory=list)
    bseg: list[dict] = field(default_factory=list)
    ground_truth_log: list[dict] = field(default_factory=list)
    mapping_coverage: Counter = field(default_factory=Counter)


def _split_ts(ts: str) -> tuple[str, str]:
    """BPI2019 timestamps are ISO 8601 UTC with millisecond precision,
    e.g. '2018-01-02T12:53:00.000Z'. Splits into SAP-style DATS (YYYYMMDD)
    and TIMS (HHMMSS)."""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})", ts)
    if not m:
        return "", ""
    y, mo, d, h, mi, s = m.groups()
    return f"{y}{mo}{d}", f"{h}{mi}{s}"


def _pstyp(item_category: str) -> str:
    return _ITEM_CATEGORY_TO_PSTYP.get(item_category.strip().lower(), "0")


def shred_traces(traces) -> ShreddedTables:
    out = ShreddedTables()
    seen_ebeln: set[str] = set()
    seen_lifnr: set[str] = set()

    changenr_seq = count(1)
    mblnr_seq = count(4900000001)
    belnr_seq = count(5100000001)
    bkpf_belnr_seq = count(6100000001)

    for trace in traces:
        ebeln = trace.purchasing_document
        ebelp = trace.item
        lifnr = trace.vendor

        if lifnr and lifnr not in seen_lifnr:
            seen_lifnr.add(lifnr)
            out.lfa1.append({"LIFNR": lifnr, "NAME1": trace.vendor_name})

        if ebeln and ebeln not in seen_ebeln:
            seen_ebeln.add(ebeln)
            out.ekko.append({
                "EBELN": ebeln,
                "BUKRS": trace.company,
                "BSART": (trace.document_type[:4] or "NB").upper().replace(" ", ""),
                "LIFNR": lifnr,
            })

        out.ekpo.append({
            "EBELN": ebeln,
            "EBELP": ebelp,
            "PSTYP": _pstyp(trace.item_category),
            "WEBRE": "X" if trace.gr_based_inv_verif else "",
        })

        rbkp_belnr_for_case: str | None = None
        mkpf_mblnr_for_case: str | None = None

        for event in trace.events:
            date_, time_ = _split_ts(event.timestamp)
            gjahr = date_[:4] if date_ else ""
            activity = event.activity

            if activity == "Create Purchase Order Item":
                out.cdhdr.append(_cdhdr(next(changenr_seq), ebeln, event.user, date_, time_))
                out.cdpos.append(_cdpos(out.cdhdr[-1]["CHANGENR"], "EKPO", "EBELP", "I", ebelp))
                out.mapping_coverage["Create Purchase Order Item -> EKPO/CDHDR/CDPOS"] += 1

            elif activity == "Vendor creates invoice":
                belnr = f"{next(belnr_seq)}"
                rbkp_belnr_for_case = belnr
                out.rbkp.append({
                    "BELNR": belnr, "GJAHR": gjahr, "LIFNR": lifnr,
                    "RMWWR": event.cumulative_net_worth_eur,
                    "CPUDT": date_, "CPUTM": time_,
                })
                out.rseg.append({
                    "BELNR": belnr, "GJAHR": gjahr, "BUZEI": "1",
                    "EBELN": ebeln, "EBELP": ebelp,
                    "WRBTR": event.cumulative_net_worth_eur,
                })
                out.mapping_coverage["Vendor creates invoice -> RBKP/RSEG"] += 1

            elif activity == "Record Goods Receipt":
                mblnr = f"{next(mblnr_seq)}"
                mkpf_mblnr_for_case = mblnr
                out.mkpf.append({"MBLNR": mblnr, "MJAHR": gjahr, "CPUDT": date_, "CPUTM": time_})
                out.mseg.append({
                    "MBLNR": mblnr, "MJAHR": gjahr, "ZEILE": "1",
                    "EBELN": ebeln, "EBELP": ebelp, "BWART": "101",
                    "MENGE": "1",  # placeholder — see mapping.yaml known_gaps: BPI2019 has no item-level quantity
                    "DMBTR": event.cumulative_net_worth_eur,
                })
                out.ekbe.append({
                    "EBELN": ebeln, "EBELP": ebelp, "VGABE": "1",
                    "GJAHR": gjahr, "BELNR": mblnr, "BUDAT": date_,
                    "CPUDT": date_, "CPUTM": time_,
                })
                out.mapping_coverage["Record Goods Receipt -> MKPF/MSEG/EKBE"] += 1

            elif activity == "Record Invoice Receipt":
                out.ekbe.append({
                    "EBELN": ebeln, "EBELP": ebelp, "VGABE": "2",
                    "GJAHR": gjahr, "BELNR": rbkp_belnr_for_case or "",
                    "BUDAT": date_, "CPUDT": date_, "CPUTM": time_,
                })
                out.mapping_coverage["Record Invoice Receipt -> EKBE"] += 1

            elif activity == "Record Service Entry Sheet":
                # Real SAP: service entry sheets (ML81N / ESSR-ESLL) are
                # functionally the service-procurement analogue of a goods
                # receipt, and post to EKBE under the same VGABE=1 as a
                # material GR. ESSR/ESLL themselves are out of this KB's
                # P2P table scope, so no MKPF/MSEG is synthesized here —
                # documented simplification, not a claim those tables exist.
                out.ekbe.append({
                    "EBELN": ebeln, "EBELP": ebelp, "VGABE": "1",
                    "GJAHR": gjahr, "BELNR": "", "BUDAT": date_,
                    "CPUDT": date_, "CPUTM": time_,
                })
                out.mapping_coverage["Record Service Entry Sheet -> EKBE (VGABE=1, no MKPF/MSEG)"] += 1

            elif activity == "Clear Invoice":
                # Simplification: synthesizes the clearing (payment)
                # accounting document directly rather than modeling the
                # full BKPF/BSEG chain from the original invoice posting
                # forward — good enough to demonstrate a 'Clear Vendor
                # Invoice' activity node, not a full FI mirror.
                belnr = f"{next(bkpf_belnr_seq)}"
                out.bkpf.append({
                    "BUKRS": trace.company, "BELNR": belnr, "GJAHR": gjahr,
                    "BLART": "KZ", "BUDAT": date_, "CPUDT": date_, "CPUTM": time_,
                })
                out.bseg.append({
                    "BUKRS": trace.company, "BELNR": belnr, "GJAHR": gjahr, "BUZEI": "1",
                    "KOART": "K", "LIFNR": lifnr,
                    "DMBTR": event.cumulative_net_worth_eur,
                    "AUGDT": date_, "AUGBL": belnr,
                })
                out.mapping_coverage["Clear Invoice -> BKPF/BSEG (simplified clearing doc)"] += 1

            elif activity.startswith("SRM:"):
                out.cdhdr.append(_cdhdr(next(changenr_seq), ebeln, event.user, date_, time_))
                out.cdpos.append(_cdpos(out.cdhdr[-1]["CHANGENR"], "EBAN", "SRM_STATUS", "U", activity))
                out.mapping_coverage["SRM:* -> CDHDR/CDPOS (documented proxy)"] += 1

            else:
                out.cdhdr.append(_cdhdr(next(changenr_seq), ebeln, event.user, date_, time_))
                out.cdpos.append(_cdpos(out.cdhdr[-1]["CHANGENR"], "EKPO", "UNMAPPED_ACTIVITY", "U", activity))
                out.mapping_coverage[f"UNMAPPED: {activity!r} -> CDHDR/CDPOS fallback"] += 1

            out.ground_truth_log.append({
                "case_id": trace.case_id,
                "activity": activity,
                "timestamp": event.timestamp,
                "user": event.user,
                "cumulative_net_worth_eur": event.cumulative_net_worth_eur,
            })

    return out


def _cdhdr(changenr: int, ebeln: str, username: str, date_: str, time_: str) -> dict:
    return {
        "OBJECTCLAS": _OBJECTCLAS_PO,
        "OBJECTID": ebeln.rjust(10, "0"),
        "CHANGENR": f"{changenr:010d}",
        "USERNAME": username,
        "UDATE": date_,
        "UTIME": time_,
    }


def _cdpos(changenr: str, tabname: str, fname: str, chngind: str, value_new: str) -> dict:
    return {
        "CHANGENR": changenr,
        "TABNAME": tabname,
        "FNAME": fname,
        "CHNGIND": chngind,
        "VALUE_NEW": value_new,
    }
