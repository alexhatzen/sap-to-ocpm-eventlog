"""Unit tests for the event log constructor domain layer.

Two kinds of coverage: hand-built minimal table dicts for precise
control over edge cases (ambiguous multi-item attribution, undated
events, the BSEG/AWKEY limitation), and a full run against the real
checked-in BPI2019 fixture as an end-to-end integration-style check
that stays in the unit suite because the fixture is static and
offline.
"""
from __future__ import annotations

from pathlib import Path

from sap_ocpm.constructor import (
    build_cases,
    build_ocel,
    derive_activities,
    flag_additional_gaps,
    load_tables_from_fixture,
    validate_ocel,
)
from sap_ocpm.constructor.timestamp_resolution import resolve_timestamp

FIXTURE_DIR = Path(__file__).parents[2] / "data" / "fixtures" / "bpi2019_sample"


# --- timestamp_resolution -------------------------------------------

def test_resolve_timestamp_date_and_time():
    assert resolve_timestamp("20190102", "125300") == "2019-01-02T12:53:00"


def test_resolve_timestamp_date_only():
    assert resolve_timestamp("20190102") == "2019-01-02T00:00:00"


def test_resolve_timestamp_missing_returns_none_not_fake_midnight():
    assert resolve_timestamp("") is None
    assert resolve_timestamp("notadate") is None


# --- activity_derivation: single-item PO (unambiguous) -------------

def _single_item_tables():
    return {
        "ekpo": [{"EBELN": "PO1", "EBELP": "00001"}],
        "ekbe": [{"EBELN": "PO1", "EBELP": "00001", "VGABE": "1", "BELNR": "M1", "BUDAT": "20190101", "CPUDT": "20190101", "CPUTM": "080000"}],
        "mkpf": [{"MBLNR": "M1", "MJAHR": "2019"}],
        "mseg": [], "rbkp": [], "rseg": [], "cdhdr": [], "cdpos": [], "lfa1": [], "bkpf": [], "bseg": [],
    }


def test_ekbe_vgabe1_with_matching_mkpf_is_goods_receipt():
    events, gaps = derive_activities(_single_item_tables())
    assert events[0].activity == "Record Goods Receipt"
    assert events[0].ebeln == "PO1" and events[0].ebelp == "00001"


def test_ekbe_vgabe1_without_matching_mkpf_is_service_entry_sheet():
    tables = _single_item_tables()
    tables["ekbe"][0]["BELNR"] = "NOT_A_REAL_MBLNR"
    events, gaps = derive_activities(tables)
    assert events[0].activity == "Record Service Entry Sheet"


# --- activity_derivation: multi-item ambiguity ----------------------

def _multi_item_cdhdr_tables():
    return {
        "ekpo": [
            {"EBELN": "PO2", "EBELP": "00001"},
            {"EBELN": "PO2", "EBELP": "00002"},
        ],
        "cdhdr": [{"OBJECTCLAS": "EINKBELEG", "OBJECTID": "0000000PO2", "CHANGENR": "1", "USERNAME": "u1", "UDATE": "20190101", "UTIME": "090000"}],
        "cdpos": [{"CHANGENR": "1", "TABNAME": "EBAN", "FNAME": "SRM_STATUS", "CHNGIND": "U", "VALUE_NEW": "SRM: Created"}],
        "ekbe": [], "mkpf": [], "mseg": [], "rbkp": [], "rseg": [], "lfa1": [], "bkpf": [], "bseg": [],
    }


def test_multi_item_po_cdhdr_event_excluded_from_item_cases_but_kept_for_order():
    tables = _multi_item_cdhdr_tables()
    tables["cdhdr"][0]["OBJECTID"] = "PO2".rjust(10, "0")
    events, gaps = derive_activities(tables)

    assert len(events) == 1
    assert events[0].ebelp is None  # header-only, ambiguous
    assert any(g.category == "ambiguous_item_attribution" for g in gaps)

    item_cases = build_cases(events, "item")
    order_cases = build_cases(events, "order")
    assert item_cases == {}  # excluded — cannot safely attribute to one item
    assert "PO2" in order_cases and len(order_cases["PO2"]) == 1


# --- activity_derivation: BSEG has no clean EBELN -------------------

def test_bseg_clearing_event_has_no_ebeln_and_is_flagged():
    tables = _single_item_tables()
    tables["bseg"] = [{"LIFNR": "V1", "AUGDT": "20190201", "DMBTR": "50.0"}]
    events, gaps = derive_activities(tables)

    clear_events = [e for e in events if e.activity == "Clear Vendor Invoice"]
    assert len(clear_events) == 1
    assert clear_events[0].ebeln == ""
    assert any(g.category == "known_limitation" and "AWKEY" in g.description for g in gaps)


# --- gap_flagging -----------------------------------------------------

def test_flag_additional_gaps_reports_undated_events():
    tables = _single_item_tables()
    tables["ekbe"][0]["CPUDT"] = ""
    tables["ekbe"][0]["BUDAT"] = ""
    events, _ = derive_activities(tables)
    gaps = flag_additional_gaps(events)
    assert any(g.category == "undated_events" for g in gaps)


# --- ocel_writer --------------------------------------------------

def test_build_ocel_vendor_only_event_relates_only_to_vendor_object():
    tables = _single_item_tables()
    tables["bseg"] = [{"LIFNR": "V1", "AUGDT": "20190201", "DMBTR": "50.0"}]
    events, _ = derive_activities(tables)
    spec = build_ocel(events, granularity="item")

    clear_event = [e for e in spec.events if e.type == "Clear Vendor Invoice"][0]
    assert clear_event.object_ids == ["VENDOR:V1"]

    result = validate_ocel(spec)
    assert result.valid


def test_build_ocel_item_granularity_creates_item_objects():
    events, _ = derive_activities(_single_item_tables())
    spec = build_ocel(events, granularity="item")
    assert "PurchaseOrderItem" in spec.object_types
    item_objs = [o for o in spec.objects if o.type == "PurchaseOrderItem"]
    assert item_objs and item_objs[0].id == "ITEM:PO1_00001"


def test_build_ocel_order_granularity_has_no_item_objects():
    events, _ = derive_activities(_single_item_tables())
    spec = build_ocel(events, granularity="order")
    assert "PurchaseOrderItem" not in spec.object_types


# --- end-to-end against the real checked-in fixture --------------------

def test_end_to_end_against_real_fixture_produces_valid_ocel():
    tables = load_tables_from_fixture(FIXTURE_DIR)
    events, gaps = derive_activities(tables)
    gaps += flag_additional_gaps(events)

    assert len(events) > 1000  # real fixture has thousands of events, not a 3-activity toy log
    activity_names = {e.activity for e in events}
    assert len(activity_names) >= 10  # multi-source derivation, not just header dates

    spec = build_ocel(events, granularity="item")
    result = validate_ocel(spec)
    assert result.valid, result.errors

    item_cases = build_cases(events, "item")
    # every EKPO row is a distinct item; item-level case count must match exactly
    assert len(item_cases) == len(tables["ekpo"])

    order_cases = build_cases(events, "order")
    assert len(order_cases) == len(tables["ekko"])

    assert gaps  # a real run over real messy data always has something to disclose
