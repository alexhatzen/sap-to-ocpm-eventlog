"""Unit tests for the BPI2019 shredder — offline, using synthetic
Bpi2019Trace/Bpi2019Event fixtures, so this suite never touches the
network. The live streaming path is exercised separately (manually /
in the fixture-build step), not in CI.
"""
from __future__ import annotations

from sap_ocpm.dataprep.download_bpi2019 import Bpi2019Event, Bpi2019Trace
from sap_ocpm.dataprep.shred_to_sap_tables import shred_traces


def _trace(case_id, ebeln, ebelp, vendor, events, **overrides) -> Bpi2019Trace:
    defaults = dict(
        case_id=case_id, purchasing_document=ebeln, item=ebelp,
        vendor=vendor, vendor_name=f"name_{vendor}", company="0001",
        document_type="Standard PO", item_category="3-way match, invoice before GR",
        item_type="Standard", gr_based_inv_verif=True, goods_receipt=True,
        events=events,
    )
    defaults.update(overrides)
    return Bpi2019Trace(**defaults)


def _event(activity, ts, user="user_1", worth=100.0) -> Bpi2019Event:
    return Bpi2019Event(activity=activity, timestamp=ts, user=user, cumulative_net_worth_eur=worth)


def test_create_po_item_populates_ekko_ekpo_and_cdhdr_cdpos():
    trace = _trace(
        "EB1_00001", "EB1", "00001", "V1",
        [_event("Create Purchase Order Item", "2019-01-01T10:00:00.000Z")],
    )
    result = shred_traces([trace])

    assert result.ekko == [{"EBELN": "EB1", "BUKRS": "0001", "BSART": "STAN", "LIFNR": "V1"}]
    assert result.ekpo[0]["EBELN"] == "EB1"
    assert result.ekpo[0]["EBELP"] == "00001"
    assert len(result.cdhdr) == 1
    assert result.cdhdr[0]["UDATE"] == "20190101"
    assert result.cdhdr[0]["UTIME"] == "100000"
    assert result.cdpos[0]["TABNAME"] == "EKPO"


def test_two_items_same_po_produce_one_ekko_row():
    events = [_event("Create Purchase Order Item", "2019-01-01T10:00:00.000Z")]
    t1 = _trace("EB1_00001", "EB1", "00001", "V1", events)
    t2 = _trace("EB1_00002", "EB1", "00002", "V1", events)
    result = shred_traces([t1, t2])

    assert len(result.ekko) == 1
    assert len(result.ekpo) == 2


def test_goods_receipt_produces_mkpf_mseg_and_ekbe_vgabe1():
    trace = _trace(
        "EB1_00001", "EB1", "00001", "V1",
        [_event("Record Goods Receipt", "2019-01-05T08:00:00.000Z")],
    )
    result = shred_traces([trace])

    assert len(result.mkpf) == 1
    assert len(result.mseg) == 1
    assert result.mseg[0]["BWART"] == "101"
    assert result.ekbe[0]["VGABE"] == "1"
    assert result.ekbe[0]["BELNR"] == result.mkpf[0]["MBLNR"]


def test_invoice_then_receipt_links_ekbe_vgabe2_to_rbkp():
    trace = _trace(
        "EB1_00001", "EB1", "00001", "V1",
        [
            _event("Vendor creates invoice", "2019-01-10T09:00:00.000Z"),
            _event("Record Invoice Receipt", "2019-01-10T09:05:00.000Z"),
        ],
    )
    result = shred_traces([trace])

    assert len(result.rbkp) == 1
    assert len(result.rseg) == 1
    ir_row = [e for e in result.ekbe if e["VGABE"] == "2"][0]
    assert ir_row["BELNR"] == result.rbkp[0]["BELNR"]


def test_clear_invoice_produces_bkpf_bseg_with_clearing_fields():
    trace = _trace(
        "EB1_00001", "EB1", "00001", "V1",
        [_event("Clear Invoice", "2019-02-01T12:00:00.000Z", worth=250.0)],
    )
    result = shred_traces([trace])

    assert len(result.bkpf) == 1
    assert result.bkpf[0]["BLART"] == "KZ"
    assert result.bseg[0]["AUGDT"] == "20190201"
    assert result.bseg[0]["DMBTR"] == 250.0


def test_service_entry_sheet_maps_to_ekbe_without_material_document():
    trace = _trace(
        "EB1_00001", "EB1", "00001", "V1",
        [_event("Record Service Entry Sheet", "2019-01-06T08:00:00.000Z")],
    )
    result = shred_traces([trace])

    assert result.mkpf == []
    assert result.ekbe[0]["VGABE"] == "1"


def test_srm_activity_falls_to_documented_cdhdr_cdpos_proxy():
    trace = _trace(
        "EB1_00001", "EB1", "00001", "V1",
        [_event("SRM: Created", "2019-01-01T09:00:00.000Z")],
    )
    result = shred_traces([trace])

    assert result.cdpos[0]["TABNAME"] == "EBAN"
    assert result.cdpos[0]["FNAME"] == "SRM_STATUS"
    assert "SRM:* -> CDHDR/CDPOS (documented proxy)" in result.mapping_coverage


def test_unrecognized_activity_hits_generic_fallback_and_is_reported():
    trace = _trace(
        "EB1_00001", "EB1", "00001", "V1",
        [_event("Some Brand New Activity Nobody Mapped", "2019-01-01T09:00:00.000Z")],
    )
    result = shred_traces([trace])

    assert result.cdpos[0]["FNAME"] == "UNMAPPED_ACTIVITY"
    assert result.cdpos[0]["VALUE_NEW"] == "Some Brand New Activity Nobody Mapped"
    assert any(k.startswith("UNMAPPED:") for k in result.mapping_coverage)


def test_ground_truth_log_preserves_every_original_event_unmodified():
    events = [
        _event("Create Purchase Order Item", "2019-01-01T10:00:00.000Z"),
        _event("Record Goods Receipt", "2019-01-05T08:00:00.000Z"),
    ]
    trace = _trace("EB1_00001", "EB1", "00001", "V1", events)
    result = shred_traces([trace])

    assert len(result.ground_truth_log) == 2
    assert result.ground_truth_log[0]["activity"] == "Create Purchase Order Item"
    assert result.ground_truth_log[1]["activity"] == "Record Goods Receipt"


def test_new_vendor_produces_lfa1_row_once():
    events = [_event("Create Purchase Order Item", "2019-01-01T10:00:00.000Z")]
    t1 = _trace("EB1_00001", "EB1", "00001", "V1", events)
    t2 = _trace("EB2_00001", "EB2", "00001", "V1", events)  # same vendor, different PO
    result = shred_traces([t1, t2])

    assert len(result.lfa1) == 1
    assert result.lfa1[0]["LIFNR"] == "V1"
