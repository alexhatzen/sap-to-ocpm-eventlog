"""Streams the public BPI Challenge 2019 event log and yields parsed
traces without requiring the full ~729MB XES file to be downloaded.

Source: van Dongen, B.F. (2019). BPI Challenge 2019. Version 1.
4TU.ResearchData. CC BY 4.0.
DOI: 10.4121/uuid:d06aff4b-79f0-45e6-8ec8-e19730c248f1
Direct file (verified via the figshare API backing 4TU.ResearchData,
article id 12715853): https://ndownloader.figshare.com/files/24072995

The dataset ships as a single IEEE-XES file with one <trace> per PO
item (case) containing an ordered list of <event> elements. Traces
appear sequentially in document order, so a streaming SAX parser can
collect the first N traces and then stop reading — no need to hold the
full file in memory or on disk for a fixture-sized sample.
"""
from __future__ import annotations

import xml.sax
from collections.abc import Iterator
from dataclasses import dataclass, field

import requests

BPI2019_URL = "https://ndownloader.figshare.com/files/24072995"

# Trace-level (case) attribute keys as they literally appear in the XES file.
TRACE_ATTR_KEYS = {
    "Spend area text", "Company", "Document Type", "Sub spend area text",
    "Purchasing Document", "Purch. Doc. Category name", "Vendor",
    "Item Type", "Item Category", "Spend classification text", "Source",
    "Name", "GR-Based Inv. Verif.", "Item", "concept:name", "Goods Receipt",
}

# Event-level attribute keys.
EVENT_ATTR_KEYS = {
    "User", "org:resource", "concept:name", "Cumulative net worth (EUR)",
    "time:timestamp",
}


@dataclass
class Bpi2019Event:
    activity: str
    timestamp: str  # ISO 8601, as given in the source (UTC, millisecond precision)
    user: str
    cumulative_net_worth_eur: float


@dataclass
class Bpi2019Trace:
    case_id: str  # concept:name, e.g. "2000000000_00001" = Purchasing Document + "_" + Item
    purchasing_document: str
    item: str
    vendor: str
    vendor_name: str
    company: str
    document_type: str
    item_category: str
    item_type: str
    gr_based_inv_verif: bool
    goods_receipt: bool
    events: list[Bpi2019Event] = field(default_factory=list)


class _StopStreaming(Exception):
    """Raised internally to unwind the SAX parser once enough traces are collected."""


class _Bpi2019Handler(xml.sax.ContentHandler):
    def __init__(self, max_traces: int, on_trace) -> None:
        super().__init__()
        self.max_traces = max_traces
        self.on_trace = on_trace
        self.trace_count = 0
        self._in_trace = False
        self._trace_attrs: dict[str, str] = {}
        self._events: list[Bpi2019Event] = []
        self._in_event = False
        self._event_attrs: dict[str, str] = {}

    def startElement(self, name, attrs):
        if name == "trace":
            self._in_trace = True
            self._trace_attrs = {}
            self._events = []
        elif name == "event":
            self._in_event = True
            self._event_attrs = {}
        elif name in ("string", "boolean", "date", "float", "int") and "key" in attrs:
            key = attrs.get("key")
            value = attrs.get("value")
            if self._in_event and key in EVENT_ATTR_KEYS:
                self._event_attrs[key] = value
            elif self._in_trace and not self._in_event and key in TRACE_ATTR_KEYS:
                self._trace_attrs[key] = value

    def endElement(self, name):
        if name == "event":
            self._in_event = False
            self._events.append(
                Bpi2019Event(
                    activity=self._event_attrs.get("concept:name", ""),
                    timestamp=self._event_attrs.get("time:timestamp", ""),
                    user=self._event_attrs.get("org:resource", ""),
                    cumulative_net_worth_eur=float(
                        self._event_attrs.get("Cumulative net worth (EUR)", 0.0) or 0.0
                    ),
                )
            )
        elif name == "trace":
            self._in_trace = False
            a = self._trace_attrs
            trace = Bpi2019Trace(
                case_id=a.get("concept:name", ""),
                purchasing_document=a.get("Purchasing Document", ""),
                item=a.get("Item", ""),
                vendor=a.get("Vendor", ""),
                vendor_name=a.get("Name", ""),
                company=a.get("Company", ""),
                document_type=a.get("Document Type", ""),
                item_category=a.get("Item Category", ""),
                item_type=a.get("Item Type", ""),
                gr_based_inv_verif=(a.get("GR-Based Inv. Verif.", "false") == "true"),
                goods_receipt=(a.get("Goods Receipt", "false") == "true"),
                events=self._events,
            )
            self.on_trace(trace)
            self.trace_count += 1
            if self.trace_count >= self.max_traces:
                raise _StopStreaming()


def stream_bpi2019_traces(max_traces: int = 300, url: str = BPI2019_URL) -> Iterator[Bpi2019Trace]:
    """Yields up to `max_traces` traces from the BPI2019 XES file, closing
    the HTTP connection as soon as enough have been collected rather than
    downloading the full ~729MB file."""
    collected: list[Bpi2019Trace] = []
    handler = _Bpi2019Handler(max_traces, collected.append)
    parser = xml.sax.make_parser()
    parser.setContentHandler(handler)

    with requests.get(url, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        try:
            for chunk in resp.iter_content(chunk_size=65536):
                if chunk:
                    parser.feed(chunk)
        except _StopStreaming:
            pass
        finally:
            resp.close()

    yield from collected
