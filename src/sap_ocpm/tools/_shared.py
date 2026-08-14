"""Shared plumbing for the deterministic tools.

All five tools in this package operate on the same loaded, validated
knowledge base. Loading is cheap (30 small YAML files) but there's no
reason to re-parse it on every tool call, so it's cached here.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from sap_ocpm.kb.loader import DEFAULT_TABLES_DIR, KnowledgeBase, load_knowledge_base


@lru_cache(maxsize=None)
def get_kb(tables_dir: Path | str | None = None) -> KnowledgeBase:
    return load_knowledge_base(tables_dir or DEFAULT_TABLES_DIR)


def _reset_kb_cache_for_tests() -> None:
    """Test-only escape hatch so tests can point at a fixture KB dir."""
    get_kb.cache_clear()
