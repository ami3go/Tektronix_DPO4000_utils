"""Framework-neutral, serialized and read-only DPO4000 MCP gateway.

All VISA calls run on exactly one executor thread with one retained session.
An operation cannot overlap another MCP operation. A cancelled MCP request does
not release the busy lease until the underlying non-interruptible VISA call
actually completes.

IMPORTANT: this gateway does not yet coordinate with DPO4000 Desk, other
processes, or third-party VISA clients. Do not enable instrument access while
another program controls the instrument.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager
from dataclasses import asdict
import math
from threading import Lock
from typing import Any, Callable

from ..errors import is_transport_error
from ..live_stream import minmax_indices
from ..read_only_guard import ReadOnlyVisaSession
from ..read_only_waveform import read_preconfigured_waveform
from ..session import scope_session


class ScopeBusyError(RuntimeError):
    """Another operation already owns this gateway's instrument lease."""


class ScopeIOForbiddenError(RuntimeError):
    """Physical instrument I/O is not enabled for this server."""


class ScopeGatewayClosedError(RuntimeError):
    """The gateway is shutting down or has closed."""


_READ_OPERATIONS = frozenset(
    {
        "identity",
        "channels",
        "measurement_slots",
        "trigger",
        "acquisition",
        "capture_preconfigured",
    }
)

_MAX_CAPTURE_POINTS = 1000
_MAX_PREVIEW_POINTS = 256


def _require_positive_int(value: Any, *, name: str, maximum: int) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer from 1 to {maximum}")
    return value


def _validate_request(name: str, params: dict[str, Any]) -> None:
    if name not in _READ_OPERATIONS:
        raise ValueError(f"Unsupported read-only operation: {name!r}")
    required = (
        {"max_points", "preview_points"} if name == "capture_preconfigured" else set()
    )
    if set(params) != required:
        raise ValueError(
            f"{name}: unexpected or missing parameters; expected {sorted(required)}"
        )
    if name == "capture_preconfigured":
        _require_positive_int(
            params["max_points"], name="max_points", maximum=_MAX_CAPTURE_POINTS
        )
        _require_positive_int(
            params["preview_points"], name="preview_points", maximum=_MAX_PREVIEW_POINTS
        )


def _read_preconfigured(scope: Any, max_points: int, preview_points: int) -> dict[str, Any]:
    """Read existing outgoing data, with no channel/range/encoding setup writes."""
    guarded = ReadOnlyVisaSession(scope.ensure_connected())
    wave = read_preconfigured_waveform(guarded, max_points=max_points)
    volts = [wave.voltage_at(index) for index in range(wave.sample_count)]
    if not volts or not all(math.isfinite(v) for v in volts):
        raise ValueError("Waveform contains no finite voltage samples")
    indices = minmax_indices(wave.samples, min(preview_points, wave.sample_count))
    preview = [
        {"time_s": wave.time_at(index), "voltage_v": volts[index]} for index in indices
    ]
    return {
        "source": wave.source,
        "label": wave.label,
        "sample_count": wave.sample_count,
        "start_index": wave.start_index,
        "stop_index": wave.stop_index,
        "acquired_at_utc": wave.acquired_at.isoformat(),
        "time_step_s": wave.preamble.x_increment,
        "voltage_min_v": min(volts),
        "voltage_max_v": max(volts),
        "voltage_mean_v": sum(volts) / len(volts),
        "voltage_rms_v": math.sqrt(sum(v * v for v in volts) / len(volts)),
        "preview": preview,
        "preview_decimated": len(preview) < wave.sample_count,
        "transfer_mode": "strict_preconfigured_query_only",
        "continuous_adc_stream": False,
    }


def _read_operation(scope: Any, name: str, params: dict[str, Any]) -> dict[str, Any]:
    """Dispatch only audited public readback calls; no arbitrary SCPI or attr lookup."""
    if name == "identity":
        return {"idn": scope.query_identity()}
    if name == "channels":
        return {
            "channels": {
                f"CH{ch}": scope.get_channel_configuration(ch) for ch in range(1, 5)
            }
        }
    if name == "measurement_slots":
        return {
            "measurement_slots": {
                str(slot): asdict(setup)
                for slot, setup in scope.get_all_measurement_setups().items()
            }
        }
    if name == "trigger":
        return {"trigger": scope.get_trigger_configuration()}
    if name == "acquisition":
        return {"acquisition": scope.get_acquisition_setup()}
    if name == "capture_preconfigured":
        return _read_preconfigured(scope, **params)
    raise ValueError(f"Unsupported operation: {name!r}")


class ReadOnlyGateway:
    """Headless single-worker scope owner, with explicit opt-in for all VISA I/O.

    `session_factory(resource)` is injectable for offline tests. The default
    retains one `scope_session` within the dedicated executor thread. Tool
    handlers never receive a raw driver or PyVISA handle.
    """

    def __init__(
        self,
        resource: str | None = None,
        *,
        allow_instrument_io: bool = False,
        timeout_ms: int = 20_000,
        session_factory: Callable[[str], AbstractContextManager[Any]] | None = None,
    ) -> None:
        if type(timeout_ms) is not int or not 1 <= timeout_ms <= 600_000:
            raise ValueError("timeout_ms must be an integer from 1 to 600000")
        if resource is not None and (not isinstance(resource, str) or not resource.strip()):
            raise ValueError("resource must be a nonempty VISA resource string")
        self.resource = resource.strip() if resource else None
        self.allow_instrument_io = bool(allow_instrument_io)
        self._session_factory = session_factory or (
            lambda name: scope_session(name, timeout_ms=timeout_ms)
        )
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dpo-mcp")
        self._busy = Lock()
        self._lifecycle = Lock()
        self._closed = False
        self._session: AbstractContextManager[Any] | None = None
        self._scope: Any = None

    def status(self) -> dict[str, Any]:
        """Metadata only: never opens or probes a VISA session."""
        with self._lifecycle:
            closed = self._closed
        return {
            "server_mode": "headless_read_only",
            "resource_configured": self.resource is not None,
            "instrument_io_enabled": self.allow_instrument_io,
            "busy": self._busy.locked(),
            "closed": closed,
            "desk_session_coordination": False,
            "physical_hil_qualified": False,
        }

    def _scope_on_worker(self) -> Any:
        if self._scope is None:
            if self.resource is None:
                raise ScopeIOForbiddenError("No VISA resource configured")
            context = self._session_factory(self.resource)
            scope = context.__enter__()
            self._scope = scope
            self._session = context
        return self._scope

    def _close_on_worker(self) -> None:
        context = self._session
        self._session = None
        self._scope = None
        if context is not None:
            context.__exit__(None, None, None)

    def _execute_on_worker(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        scope = self._scope_on_worker()
        try:
            return _read_operation(scope, name, params)
        except Exception as exc:
            if is_transport_error(exc):
                try:
                    self._close_on_worker()
                except Exception:
                    pass  # Keep the original transport exception; reconnect on next call.
            raise

    async def execute(self, name: str, **params: Any) -> dict[str, Any]:
        """Execute one allowed operation; fail BUSY rather than queue indefinitely."""
        _validate_request(name, params)  # Must reject invalid input BEFORE connecting.
        if not self.allow_instrument_io or self.resource is None:
            raise ScopeIOForbiddenError(
                "Instrument I/O disabled. Start with an explicit --resource and "
                "--allow-instrument-io after confirming the scope is not in use."
            )
        with self._lifecycle:
            if self._closed:
                raise ScopeGatewayClosedError("MCP scope gateway is closed")
            if not self._busy.acquire(blocking=False):
                raise ScopeBusyError("The MCP scope worker is busy; retry later")
            try:
                future = self._executor.submit(self._execute_on_worker, name, params)
            except BaseException:
                self._busy.release()
                raise
            # Use the concurrent future, not asyncio's wrapper: cancellation of
            # a client request must not free the lease before VISA actually finishes.
            future.add_done_callback(lambda _completed: self._busy.release())
        return await asyncio.wrap_future(future)

    def close(self) -> None:
        """Close the session on its owning thread and reject all new operations."""
        with self._lifecycle:
            if self._closed:
                return
            self._closed = True
            future = self._executor.submit(self._close_on_worker)
        try:
            future.result()  # Session closes only after any active operation completes.
        finally:
            self._executor.shutdown(wait=True)


__all__ = [
    "ReadOnlyGateway",
    "ScopeBusyError",
    "ScopeGatewayClosedError",
    "ScopeIOForbiddenError",
]
