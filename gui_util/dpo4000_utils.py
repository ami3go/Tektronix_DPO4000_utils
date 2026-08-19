"""
Compatibility wrapper for older GUI/builds that import dpo4000_utils.

The real driver module is tektronix_utils.py. Keep this file in the same
folder as tektronix_utils.py and the GUI script.
"""

from tektronix_utils import *  # noqa: F401,F403
