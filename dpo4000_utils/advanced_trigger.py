"""Advanced-trigger helpers that complete the A14 driver-level surface.

This module deliberately keeps the still-unverified holdoff-by-count command out of
public APIs.  The DPO4054 path verified during A14 is holdoff-by-time via
``TRIGGER:A:HOLDOFF:VALUE``.  Capability probing is bounded by a dedicated temporary
VISA timeout so a nonexistent/misnamed SCPI query cannot inherit the driver's normal
(long) operational timeout.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .errors import DPOError, is_timeout_error, transport_exception
from .scpi_values import ensure_single_scpi_value, format_scpi_number


TRIGGER_HOLDOFF_QUERY = "TRIGGER:A:HOLDOFF:VALUE?"
DEFAULT_CAPABILITY_PROBE_TIMEOUT_MS = 500


@dataclass(frozen=True)
class CapabilityProbeResult:
    """Result from one bounded SCPI capability query.

    ``supported`` is true only when the candidate query returned and the standard
    event-status register remained clear.  ``timed_out`` distinguishes the DPO4000
    firmware quirk where an unsupported query can silently consume the VISA timeout.
    ``recovered`` confirms that the post-timeout ``*CLS`` + ``*IDN?`` health check
    completed before control returned to the caller.
    """

    query: str
    supported: bool
    response: str = ""
    timed_out: bool = False
    recovered: bool = True
    esr: int | None = None
    elapsed_s: float = 0.0


def normalize_probe_query(command: str) -> str:
    """Validate a single argument-free SCPI query suitable for capability probing."""
    text = ensure_single_scpi_value(command, field="Capability probe query").strip()
    if not text.endswith("?") or text.count("?") != 1:
        raise ValueError("Capability probe query must be one SCPI query ending in '?'.")
    if any(char.isspace() for char in text):
        raise ValueError("Capability probe query must not contain arguments or whitespace.")
    return text.upper()


def normalize_trigger_holdoff(value: str | float | int) -> str:
    """Return a finite non-negative holdoff-by-time value in seconds."""
    return format_scpi_number(value, field="Trigger holdoff", nonnegative=True)


def build_trigger_holdoff_command(value: str | float | int) -> str:
    return f"TRIGGER:A:HOLDOFF:VALUE {normalize_trigger_holdoff(value)}"


def build_trigger_holdoff_query() -> str:
    return TRIGGER_HOLDOFF_QUERY


def _parse_esr(response: Any) -> int:
    text = str(response or "").strip()
    token = text.split()[-1] if text.split() else ""
    try:
        return int(float(token))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid *ESR? response: {response!r}") from exc


class AdvancedTriggerMixin:
    """A14 holdoff and safe capability-probe extension for ``DPO4000Scope``."""

    def configure_trigger(self, config: Any, *, holdoff: str | float | int | None = None) -> None:
        """Apply an A-trigger config and optional verified holdoff-by-time value.

        Holdoff is validated before *any* instrument write, preserving the project's
        zero-I/O-on-invalid-input contract.  The trigger-type command sequence itself
        remains owned by :class:`~dpo4000_utils.control.ControlMixin`.
        """
        holdoff_command = build_trigger_holdoff_command(holdoff) if holdoff is not None else None
        super().configure_trigger(config)
        if holdoff_command is not None:
            self.ensure_connected().write(holdoff_command)

    def get_trigger_configuration(self) -> dict[str, Any]:
        """Read the current A-trigger configuration including holdoff-by-time."""
        result = dict(super().get_trigger_configuration())
        result["holdoff"] = self.get_trigger_holdoff()
        return result

    def set_trigger_holdoff(
        self,
        value: str | float | int,
        *,
        verify: bool = True,
    ) -> float | None:
        """Set A-trigger holdoff-by-time in seconds.

        A count/event holdoff mode is intentionally not exposed: its SCPI command path
        has not been verified on the DPO4054 firmware used for A14 qualification.
        """
        command = build_trigger_holdoff_command(value)
        self.ensure_connected().write(command)
        return self.get_trigger_holdoff() if verify else None

    def get_trigger_holdoff(self) -> float:
        """Read A-trigger holdoff-by-time in seconds."""
        response = self.ensure_connected().query(build_trigger_holdoff_query()).strip()
        token = response.split()[-1] if response.split() else ""
        try:
            return float(token)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid trigger holdoff response: {response!r}") from exc

    def probe_scpi_query(
        self,
        command: str,
        *,
        timeout_ms: int = DEFAULT_CAPABILITY_PROBE_TIMEOUT_MS,
    ) -> CapabilityProbeResult:
        """Probe one SCPI query with a short temporary timeout and recovery check.

        The active VISA timeout is capped only for this call and restored exactly by
        ``ConnectionMixin.temporary_timeout``.  A timed-out candidate is treated as
        unsupported, then recovered with ``*CLS`` and a bounded ``*IDN?`` health check.
        Non-timeout transport failures are not converted to "unsupported" because that
        would hide a genuinely lost session.
        """
        query = normalize_probe_query(command)
        timeout_value = int(timeout_ms)
        if timeout_value <= 0:
            raise ValueError("timeout_ms must be a positive integer")

        self.ensure_connected()
        started = time.monotonic()
        with self.temporary_timeout(timeout_value) as scoped:
            # Capability probing is diagnostic by definition. Clear stale status first
            # so the ESR sampled after the candidate belongs to this probe.
            scoped.write("*CLS")
            try:
                response = scoped.query(query).strip()
            except Exception as exc:
                if not is_timeout_error(exc):
                    if isinstance(exc, DPOError):
                        raise
                    raise transport_exception(exc, f"Probing SCPI capability {query!r}") from exc

                # The DPO4000 family can silently time out on an unsupported query.
                # Clear status and prove the session is alive before returning.
                try:
                    scoped.write("*CLS")
                    health = scoped.query("*IDN?").strip()
                except Exception as health_exc:
                    if isinstance(health_exc, DPOError):
                        raise
                    raise transport_exception(
                        health_exc,
                        f"Recovering after timed-out capability probe {query!r}",
                    ) from health_exc
                if not health:
                    raise RuntimeError(
                        f"Capability probe {query!r} timed out and recovery returned an empty *IDN? response."
                    )
                return CapabilityProbeResult(
                    query=query,
                    supported=False,
                    timed_out=True,
                    recovered=True,
                    elapsed_s=time.monotonic() - started,
                )

            try:
                esr = _parse_esr(scoped.query("*ESR?"))
            except Exception as exc:
                if is_timeout_error(exc):
                    raise transport_exception(exc, f"Reading *ESR? after capability probe {query!r}") from exc
                if isinstance(exc, DPOError):
                    raise
                raise

            supported = esr == 0
            if not supported:
                # Leave the session with a clean standard-event status register.
                scoped.write("*CLS")
            return CapabilityProbeResult(
                query=query,
                supported=supported,
                response=response,
                timed_out=False,
                recovered=True,
                esr=esr,
                elapsed_s=time.monotonic() - started,
            )


__all__ = [
    "AdvancedTriggerMixin",
    "CapabilityProbeResult",
    "DEFAULT_CAPABILITY_PROBE_TIMEOUT_MS",
    "TRIGGER_HOLDOFF_QUERY",
    "build_trigger_holdoff_command",
    "build_trigger_holdoff_query",
    "normalize_probe_query",
    "normalize_trigger_holdoff",
]
