"""Public short-lived DPO4000 session helpers."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from .errors import add_exception_note
from .instrument import DPO4054, DPO4000Scope

logger = logging.getLogger(__name__)


@contextmanager
def scope_session(
    resource_name: str,
    *,
    timeout_ms: int | None = None,
    read_termination: str | None = "\n",
    write_termination: str | None = "\n",
) -> Iterator[DPO4000Scope]:
    """Open, yield, and close one short-lived, driver-configured session.

    ``resource_name`` is intentionally explicit; the reusable library no longer
    assumes one lab instrument serial number. Cleanup failures never replace an
    exception raised by the caller's body.
    """
    scope = DPO4054(
        resource_name,
        auto_connect=False,
        timeout_ms=timeout_ms,
        read_termination=read_termination,
        write_termination=write_termination,
    )
    primary_error: BaseException | None = None
    try:
        scope.connect()
        try:
            yield scope
        except BaseException as exc:
            primary_error = exc
            raise
    finally:
        try:
            scope.disconnect()
        except BaseException as cleanup_exc:
            if primary_error is None:
                raise
            add_exception_note(primary_error, f"Scope-session cleanup failure: {cleanup_exc}")
            logger.warning(
                "Scope-session cleanup failure while propagating primary error: %s",
                cleanup_exc,
            )


__all__ = ["scope_session"]
