"""Compatibility wrapper for legacy imports.

Prefer importing from ``dpo4000_utils`` in new code:

    from dpo4000_utils import DPO4054

This wrapper keeps older scripts working when they use:

    from tektronix_utils import DPO4054
"""

from dpo4000_utils.tektronix_utils import *  # noqa: F401,F403
