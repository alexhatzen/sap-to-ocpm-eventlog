"""Puts the repo root on sys.path so tests can import the top-level
`eval` package (eval/metrics.py, eval/schema.py, eval/run_eval.py)
alongside `sap_ocpm` (already reachable via PYTHONPATH=src)."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
