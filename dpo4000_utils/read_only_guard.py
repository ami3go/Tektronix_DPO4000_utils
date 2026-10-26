"""Fail-closed query-only VISA adapter for strict, no-configuration-write HIL.

PyVISA query() implementations transmit the query through write() internally.
Only exactly one argument-free SCPI query is allowed through either entrypoint.
This does not turn a configuration-writing driver operation into a read-only one;
callers must still avoid methods such as DATA:SOURCE writes and HARDCOPY START.
"""
from __future__ import annotations

from typing import Any


class ReadOnlyViolation(RuntimeError):
    """A non-query or ambiguous SCPI operation was rejected before transport I/O."""


def require_query(command: str) -> str:
    if not isinstance(command, str):
        raise ReadOnlyViolation("SCPI query must be text")
    value = command.strip()
    if (
        not value
        or value.count("?") != 1
        or not value.endswith("?")
        or any(char in value for char in (";", "\n", "\r", "\x00"))
    ):
        raise ReadOnlyViolation(f"Strict read-only transport refused command: {value!r}")
    return value


class ReadOnlyVisaSession:
    """Proxy enforcing single-query-only SCPI transport, preserving VISA attributes."""

    def __init__(self, wrapped: Any) -> None:
        object.__setattr__(self, "_wrapped", wrapped)
        object.__setattr__(self, "query_count", 0)
        object.__setattr__(self, "blocked_count", 0)
        object.__setattr__(self, "query_log", [])

    def __getattribute__(self, name: str) -> Any:
        if name == "_wrapped":
            raise ReadOnlyViolation("Underlying unguarded VISA session is private")
        return object.__getattribute__(self, name)

    def __getattr__(self, name: str) -> Any:
        # Do not expose a raw VISA handle that could bypass the SCPI guard.
        if name in {"visalib", "session", "resource_manager", "_wrapped"}:
            raise ReadOnlyViolation(f"Raw VISA handle access is forbidden: {name}")
        return getattr(object.__getattribute__(self, "_wrapped"), name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in {"_wrapped", "query_count", "blocked_count", "query_log"}:
            object.__setattr__(self, name, value)
        else:
            setattr(object.__getattribute__(self, "_wrapped"), name, value)

    def _approve(self, command: str) -> str:
        try:
            result = require_query(command)
        except ReadOnlyViolation:
            object.__setattr__(self, "blocked_count", self.blocked_count + 1)
            raise
        object.__setattr__(self, "query_count", self.query_count + 1)
        if len(self.query_log) < 4096:
            self.query_log.append(result)
        return result

    def write(self, command: str, *args: Any, **kwargs: Any) -> Any:
        return object.__getattribute__(self, "_wrapped").write(self._approve(command), *args, **kwargs)

    def query(self, command: str, *args: Any, **kwargs: Any) -> Any:
        return object.__getattribute__(self, "_wrapped").query(self._approve(command), *args, **kwargs)

    def query_binary_values(self, command: str, *args: Any, **kwargs: Any) -> Any:
        return object.__getattribute__(self, "_wrapped").query_binary_values(self._approve(command), *args, **kwargs)

    def query_ascii_values(self, command: str, *args: Any, **kwargs: Any) -> Any:
        return object.__getattribute__(self, "_wrapped").query_ascii_values(self._approve(command), *args, **kwargs)

    def write_raw(self, *_args: Any, **_kwargs: Any) -> None:
        object.__setattr__(self, "blocked_count", self.blocked_count + 1)
        raise ReadOnlyViolation("Raw VISA writes are forbidden under strict read-only HIL")

    def write_binary_values(self, *_args: Any, **_kwargs: Any) -> None:
        object.__setattr__(self, "blocked_count", self.blocked_count + 1)
        raise ReadOnlyViolation("Binary VISA writes are forbidden under strict read-only HIL")

    def clear(self) -> None:
        object.__setattr__(self, "blocked_count", self.blocked_count + 1)
        raise ReadOnlyViolation("VISA device clear is forbidden under strict read-only HIL")

    def close(self) -> Any:
        return object.__getattribute__(self, "_wrapped").close()
