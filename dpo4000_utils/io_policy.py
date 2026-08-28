"""Shared instrument-I/O policy helpers used by high-level driver mixins."""

from __future__ import annotations

from typing import Any, Callable

from .errors import DPOError, is_transport_error, transport_exception


def optional_query(
    instrument: Any,
    command: str,
    *,
    normalizer: Callable[[Any], str] | None = None,
) -> str:
    """Query an optional firmware field without hiding a lost transport.

    A VISA/connection-style failure is treated as an unsupported optional command
    only when a follow-up ``*IDN?`` proves the session is still alive. If the
    health check also fails, a stable DPO transport exception is propagated.
    Unexpected Python exceptions are never swallowed.
    """
    try:
        response = instrument.query(command)
    except DPOError:
        raise
    except Exception as exc:
        if not is_transport_error(exc):
            raise
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
