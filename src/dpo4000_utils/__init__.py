"""Tektronix DPO4000 utility package."""

from .tektronix_utils import DPO4054, visaResourceAddr

# Generic alias for DPO4000-family scopes. The implementation remains backwards
# compatible with the original DPO4054 class used by existing scripts.
DPO4000Scope = DPO4054

__all__ = ["DPO4054", "DPO4000Scope", "visaResourceAddr"]
