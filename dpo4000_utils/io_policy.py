"""Shared instrument-I/O policy helpers used by high-level driver mixins."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from .errors import DPOError, is_transport_error, transport_exception

logger = logging.getLogger(__name__)


def _discard_pending_transfer(instrument: Any) -> None:
    """Clear the instrument's I/O buffers before reusing a session that just failed.

    A timed-out query is not necessarily an abandoned one: the instrument may still
    answer it moments later. Probing session health without clearing first can read
    that late reply, mistake it for the probe's own response, and leave every
    subsequent query one answer behind -- a whole readback scan silently shifted.
    Clearing is best effort; the probe result is what decides the outcome.
    """
    clear = getattr(instrument, "clear", None)
    if not callable(clear):
        return
    try:
        clear()
    except Exception as exc:  # noqa: BLE001 - never mask the failure being handled.
        logger.debug("Could not clear instrument I/O before health check: %s", exc)


def optional_query(
    instrument: Any,
    command: str,
    *,
    normalizer: Callable[[Any], str] | None = None,
) -> str:
    """Query an optional firmware field without hiding a lost transport.

    A VISA/connection-style failure is treated as an unsupported optional command
    only when a follow-up ``*IDN?`` proves the session is still alive. The buffers
    are cleared before that probe so a late answer to the failed command cannot be
    read as the probe's response. If the health check also fails, a stable DPO
    transport exception is propagated. Unexpected Python exceptions are never
    swallowed.
    """
    try:
        response = instrument.query(command)
    except DPOError:
        raise
    except Exception as exc:
        if not is_transport_error(exc):
            raise
        _discard_pending_transfer(instrument)
        try:
            instrument.query("*IDN?")
        except Exception as health_exc:
            if isinstance(health_exc, DPOError):
                raise
            raise transport_exception(
                health_exc,
                f"Optional query {command!r} and session health check",
            ) from health_exc
        return ""

    if normalizer is not None:
        return normalizer(response)
    return str(response).strip()


def required_query(
    instrument: Any,
    command: str,
    *,
    normalizer: Callable[[Any], str] | None = None,
    operation: str | None = None,
) -> str:
    """Query a required field and translate backend transport exceptions."""
    try:
        response = instrument.query(command)
    except DPOError:
        raise
    except Exception as exc:
        if is_transport_error(exc):
            raise transport_exception(exc, operation or f"Query {command!r}") from exc
        raise
    if normalizer is not None:
        return normalizer(response)
    return str(response).strip()


__all__ = ["optional_query", "required_query"]
