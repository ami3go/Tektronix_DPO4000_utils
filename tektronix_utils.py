"""Compatibility wrapper for older scripts run from a repository checkout.

Prefer importing from dpo4000_utils instead:

    from dpo4000_utils import DPO4054
"""

from pathlib import Path
import sys

_SRC = Path(__file__).resolve().parent / "src"
if _SRC.exists():
    sys.path.insert(0, str(_SRC))

from dpo4000_utils.tektronix_utils import *  # noqa: F401,F403,E402
