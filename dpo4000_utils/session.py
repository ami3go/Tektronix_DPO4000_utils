"""Public short-lived DPO4000 session helpers.

GUI applications and other front ends should use :func:`scope_session` instead of
reaching into the driver's internal PyVISA handle.  Keeping VISA lifecycle and
session tuning in the driver package gives every UI a single, testable boundary
to the instrument layer.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from .connection import visaResourceAddr
from .instrument import DPO4000Scope, DPO4054


@contextmanager
def scope_session(
    resource_name: str = visaResourceAddr,
    *,
    timeout_ms: int | None = None,
    read_termination: str | None = "\n",
    write_termination: str | None = "\n",
) -> Iterator[DPO4000Scope]:
    """Open, yield, and close one short-lived, driver-configured session."""
    scope = DPO4054(
        resource_name,
        auto_connect=False,
        timeout_ms=timeout_ms,
        read_termination=read_termination,
        write_termination=write_termination,
    )
    try:
        scope.connect()
        yield scope
    finally:
        scope.disconnect()


__all__ = ["scope_session"]
