"""Canonical acquisition-mode readback handling for DPO4000 instruments.

Tektronix scopes can return minimum-form SCPI keywords when verbose responses
are disabled.  The application and public driver expose only the canonical
acquisition labels; abbreviated readback tokens are decoded only at the
instrument boundary and are not accepted as user/API command input.
"""

from __future__ import annotations

from typing import Any

from .control import ACQUISITION_MODES, normalize_scope_response_text
from .errors import DPOProtocolError


_ACQUISITION_MODE_READBACK_ALIASES = {
    "SAM": "SAMPLE",
    "PEAK": "PEAKDETECT",
    "HIR": "HIRES",
    "AVE": "AVERAGE",
    "ENV": "ENVELOPE",
}


def canonicalize_acquisition_mode_readback(value: Any) -> str:
    """Return one canonical acquisition mode from a Tektronix query response.

    Minimum-form SCPI responses such as ``HIR`` are transport/readback syntax,
    not supported application labels.  Command builders remain strict and only
    accept values from :data:`dpo4000_utils.control.ACQUISITION_MODES`.
    """
    token = normalize_scope_response_text(value).strip().upper()
    if token in ACQUISITION_MODES:
        return token

    canonical = _ACQUISITION_MODE_READBACK_ALIASES.get(token)
    if canonical is not None:
        return canonical

    raise DPOProtocolError(f"Unsupported acquisition mode readback: {value!r}.")


class AcquisitionModeReadbackMixin:
    """Canonicalize acquisition-mode values returned by :class:`ControlMixin`."""

    def get_acquisition_setup(self) -> dict[str, str]:
        values = dict(super().get_acquisition_setup())
        mode = str(values.get("mode", "")).strip()
        if mode:
            values["mode"] = canonicalize_acquisition_mode_readback(mode)
        return values

    def get_acquisition_mode(self) -> str:
        return canonicalize_acquisition_mode_readback(super().get_acquisition_mode())


__all__ = [
    "AcquisitionModeReadbackMixin",
    "canonicalize_acquisition_mode_readback",
]
