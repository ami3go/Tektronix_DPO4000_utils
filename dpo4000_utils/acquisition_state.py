"""Public acquisition/trigger-state readback for DPO4000-family scopes.

The commands in this module are documented by the Tektronix MSO4000/DPO4000
Programmer Manual. Keeping them in the reusable driver lets Automation wait for
single acquisitions without embedding SCPI in Qt code.
"""

from __future__ import annotations

from typing import Any

from .control import normalize_scope_response_text
from .io_policy import required_query

ACQUISITION_COUNT_QUERY = "ACQUIRE:NUMACQ?"
STOP_AFTER_QUERY = "ACQUIRE:STOPAFTER?"
MAX_ACQUISITION_COUNT = 2**32 - 1


def normalize_acquisition_count(response: Any) -> int:
    """Strictly parse the DPO4000 unsigned 32-bit acquisition counter.

    The counter resets after ACQUIRE:STATE RUN and some waveform-affecting
    configuration changes. It is not a lifetime acquisition identifier.
    """
    import re

    token = normalize_scope_response_text(response)
    if not re.fullmatch(r"[0-9]+", token):
        raise ValueError(f"Invalid ACQUIRE:NUMACQ readback: {response!r}")
    count = int(token)
    if count > MAX_ACQUISITION_COUNT:
        raise ValueError(f"Acquisition counter out of range: {count}")
    return count


def normalize_stop_after(response: Any) -> str:
    """Parse STOPAFTER conservatively; unknown readbacks fail closed."""
    token = normalize_scope_response_text(response).upper()
    if token in ("SEQUENCE", "SEQ"):
        return "SEQUENCE"
    if token in ("RUNSTOP", "RUNST"):
        return "RUNSTOP"
    raise ValueError(f"Invalid ACQUIRE:STOPAFTER readback: {response!r}")


ACQUISITION_STATE_QUERY = "ACQUIRE:STATE?"
BUSY_QUERY = "BUSY?"
TRIGGER_STATE_QUERY = "TRIGGER:STATE?"
TRIGGER_STATES = ("ARMED", "AUTO", "READY", "SAVE", "TRIGGER")
_TRIGGER_STATE_ALIASES = {
    "ARM": "ARMED",
    "REA": "READY",
    "SAV": "SAVE",
    "TRIG": "TRIGGER",
}


def normalize_acquisition_state(response: Any) -> bool:
    """Normalize ACQUIRE:STATE? to True while the acquisition system is running."""
    token = normalize_scope_response_text(response).strip().upper()
    if token in {"1", "ON", "RUN"}:
        return True
    if token in {"0", "OFF", "STOP"}:
        return False
    raise ValueError(f"Unexpected ACQUIRE:STATE response: {response!r}.")


def normalize_busy_state(response: Any) -> bool:
    """Normalize BUSY? to True while an extended oscilloscope operation is active."""
    token = normalize_scope_response_text(response).strip().upper()
    if token in {"1", "ON", "BUSY"}:
        return True
    if token in {"0", "OFF", "IDLE"}:
        return False
    raise ValueError(f"Unexpected BUSY response: {response!r}.")


def normalize_trigger_state(response: Any) -> str:
    """Normalize TRIGGER:STATE? tokens, including DPO4054 abbreviations."""
    token = normalize_scope_response_text(response).strip().upper()
    token = _TRIGGER_STATE_ALIASES.get(token, token)
    if token not in TRIGGER_STATES:
        raise ValueError(
            f"Unexpected TRIGGER:STATE response {response!r}; expected one of {TRIGGER_STATES}."
        )
    return token


class AcquisitionStateMixin:
    """High-level state queries used by automation and non-GUI clients."""

    def get_acquisition_count(self) -> int:
        """Read the instrument's actual acquisition counter, never a synthetic value."""
        response = required_query(
            self.ensure_connected(), ACQUISITION_COUNT_QUERY,
            operation="Reading DPO4000 acquisition counter",
        )
        return normalize_acquisition_count(response)

    def get_stop_after(self) -> str:
        """Read the configured acquisition stop mode for transactional rollback."""
        response = required_query(
            self.ensure_connected(), STOP_AFTER_QUERY,
            operation="Reading DPO4000 stop-after setting",
        )
        return normalize_stop_after(response)

    def set_stop_after(self, mode: str) -> None:
        """Write one validated stop-after setting without starting acquisition."""
        normalized = normalize_stop_after(mode)
        self.ensure_connected().write(f"ACQUIRE:STOPAFTER {normalized}")

    def get_acquisition_state(self) -> bool:
        """Return True while ACQUIRE:STATE reports running/on."""
        response = required_query(
            self.ensure_connected(),
            ACQUISITION_STATE_QUERY,
            operation="Reading acquisition state",
        )
        return normalize_acquisition_state(response)

    def is_acquiring(self) -> bool:
        """Alias for :meth:`get_acquisition_state` with predicate semantics."""
        return self.get_acquisition_state()

    def is_busy(self) -> bool:
        """Return True while BUSY? reports an extended operation in progress."""
        response = required_query(
            self.ensure_connected(),
            BUSY_QUERY,
            operation="Reading oscilloscope busy state",
        )
        return normalize_busy_state(response)

    def get_trigger_state(self) -> str:
        """Return ARMED/AUTO/READY/SAVE/TRIGGER from TRIGGER:STATE?."""
        response = required_query(
            self.ensure_connected(),
            TRIGGER_STATE_QUERY,
            operation="Reading trigger state",
        )
        return normalize_trigger_state(response)


__all__ = [
    "ACQUISITION_STATE_QUERY",
    "ACQUISITION_COUNT_QUERY",
    "STOP_AFTER_QUERY",
    "MAX_ACQUISITION_COUNT",
    "normalize_acquisition_count",
    "normalize_stop_after",
    "BUSY_QUERY",
    "TRIGGER_STATE_QUERY",
    "TRIGGER_STATES",
    "AcquisitionStateMixin",
    "normalize_acquisition_state",
    "normalize_busy_state",
    "normalize_trigger_state",
]
