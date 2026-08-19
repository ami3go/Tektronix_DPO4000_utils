"""Pytest configuration for checkout-local test runs.

The project uses a ``src/`` package layout. Installing the project with
``pip install -e .[dev]`` is still the preferred development setup, but this
fallback keeps direct commands such as ``pytest -q`` working from a fresh
checkout where the package has not been installed yet.
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"

if SRC_ROOT.is_dir():
    src_text = str(SRC_ROOT)
    if src_text not in sys.path:
        sys.path.insert(0, src_text)
