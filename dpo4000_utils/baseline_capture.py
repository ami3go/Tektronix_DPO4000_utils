"""R0-F/R0-T baseline capture against one connected DPO4000-family oscilloscope.

This module produces the functional and timing/performance baseline data required
by ``docs/regression-test-plan.md``. It only uses the public DPO4054 driver API and
follows the same reversible capture/act/restore discipline as
:mod:`dpo4000_utils.hardware_verification_core`.
"""

from __future__ import annotations

import platform
import statistics
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any, Callable

from .control import ChannelConfig, TriggerConfig, bool_from_scope_response
from .errors import DPOError
from .instrument import DPO4054
from .settings import apply_setup_string, build_scope_settings_payload

NOT_YET_COVERED: tuple[str, ...] = (
    "worker dispatch / GUI callback latency (needs a fake-clock + Qt heartbeat harness)",
    "core/full parameter refresh latency",
    "logger enqueue/write/drain throughput",
    "cancel/reconnect/shutdown latency",
    "GUI responsiveness under load (regression-test-plan.md section 7)",
    "concurrency/backpressure regression (section 8)",
    "scheduler drift/jitter regression (section 6)",
    "soak/long-duration stability (section 12)",
)


def package_version() -> str:
    try:
        return metadata.version("dpo4000-utils")
    except metadata.PackageNotFoundError:
        return "source-tree"


def commit_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            cwd=Path(__file__).resolve().parent,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip()


def firmware_from_idn(idn: str) -> str:
    for token in idn.split():
        if token.upper().startswith("FV:"):
            return token[3:]
    return ""


def build_baseline_header(resource: str, idn: str) -> dict[str, Any]:
    """Return the common schema/provenance header shared by every baseline JSON file."""
    return {
        "schema_version": 1,
        "commit_sha": commit_sha(),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "package_version": package_version(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "resource": resource,
        "idn": idn,
        "firmware": firmware_from_idn(idn),
    }


def distribution(samples: list[float]) -> dict[str, float | int]:
    """Return {min, p50, p95, p99, max, sample_count} for a list of durations."""
    if not samples:
        raise ValueError("distribution() requires at least one sample.")
    ordered = sorted(samples)
    return {
        "min": ordered[0],
        "p50": statistics.median(ordered),
        "p95": _percentile(ordered, 0.95),
        "p99": _percentile(ordered, 0.99),
        "max": ordered[-1],
        "sample_count": len(ordered),
    }


def _percentile(ordered: list[float], fraction: float) -> float:
    """Nearest-rank percentile over an already-sorted sequence."""
    if len(ordered) == 1:
        return ordered[0]
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def _time_repeated(operation: Callable[[], None], reps: int) -> list[float]:
    samples = []
    for _ in range(reps):
        started = time.perf_counter()
        operation()
        samples.append(time.perf_counter() - started)
    return samples


@dataclass
class BaselineConfig:
    resource: str
    output_dir: Path
    timeout_ms: int = 20_000
    test_channel: int = 1
    reps_standard: int = 20
    reps_heavy: int = 5
    reps_waveform_large: int = 2
    waveform_sizes: tuple[int, ...] = (1_000, 10_000, 100_000, 1_000_000, 10_000_000)
    connection_settle_delay_s: float = 2.0
    connection_warmup_max_wait_s: float = 60.0
    capability_probe_timeout_ms: int = 500


class HardwareBaselineCapture:
    """Capture R0-F/R0-T baseline data against one connected oscilloscope."""

    def __init__(self, config: BaselineConfig):
        self.config = config
        self.config.output_dir = Path(self.config.output_dir)
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        self.scope: DPO4054 | None = None

    def connect(self) -> None:
        # Unconditional settle gap: observed on the DPO4054 used to build this
        # baseline, any connect attempt immediately following any disconnect fails
        # at the RPC portmapper with no preceding gap, however light the prior
        # session was. Cheap to always pay (one settle delay on the very first,
        # cold connect too) and far simpler than tracking "was there a recent
        # disconnect" everywhere connect() is called.
        time.sleep(self.config.connection_settle_delay_s)
        self.scope = DPO4054(
            self.config.resource,
            auto_connect=False,
            timeout_ms=self.config.timeout_ms,
            read_termination="\n",
            write_termination="\n",
        )
        self.scope.connect()

    def disconnect(self) -> None:
        if self.scope is not None:
            self.scope.disconnect()
            self.scope = None

    def _require_scope(self) -> DPO4054:
        if self.scope is None:
            raise RuntimeError("Baseline capture scope is not connected.")
        return self.scope

    def _wait_for_acquisition_complete(self, scope: DPO4054) -> None:
        deadline = time.monotonic() + max(1.0, self.config.timeout_ms / 1000)
        while time.monotonic() < deadline:
            if not scope.is_acquiring():
                return
            time.sleep(0.02)
        raise TimeoutError(f"Scope did not finish acquisition within {self.config.timeout_ms} ms.")

    # ---- R0-F: functional baseline -----------------------------------------

    def capture_functional(self) -> dict[str, Any]:
        scope = self._require_scope()
        channels = {str(ch): scope.get_channel_configuration(ch) for ch in (1, 2, 3, 4)}
        reference_slots = scope.get_available_reference_slots()
        references = {
            str(slot): scope.get_reference_configuration(slot) for slot in reference_slots
        }
        bus_slots = scope.get_available_bus_slots()
        buses = {str(slot): scope.get_bus_configuration(slot) for slot in bus_slots}
        measurements = {
            str(slot): asdict(setup) for slot, setup in scope.get_all_measurement_setups().items()
        }
        return {
            "connection": {"idn": scope.query_identity()},
            "channels": channels,
            "math": scope.get_math_configuration(),
            "references": references if references else {"available": False},
            "buses": buses if buses else {"available": False},
            "measurements": measurements,
            "trigger": {
                "edge": scope.get_edge_trigger_configuration(),
                "level": scope.get_trigger_level(channel=self.config.test_channel),
            },
            "horizontal": {
                "position": scope.get_horizontal_position(),
                "record_length": scope.get_record_length(),
            },
            "acquisition": scope.get_acquisition_setup(),
            "display": scope.get_display_settings(),
            "setup_round_trip": self._verify_setup_round_trip(scope),
        }

    def _verify_setup_round_trip(self, scope: DPO4054) -> dict[str, Any]:
        instrument = scope.ensure_connected()
        before = build_scope_settings_payload(instrument)
        apply_setup_string(
            instrument,
            before["setup"],
            wait_complete=False,
            check_error=False,
            restore_delay_s=0.5,
        )
        after = build_scope_settings_payload(instrument)
        return {
            "restored": True,
            "instrument_matches": before["instrument"] == after["instrument"],
        }

    # ---- R0-T: timing/performance baseline ---------------------------------

    def capture_timing(self) -> dict[str, Any]:
        # Must run before anything else in this method: it releases and later
        # re-establishes self.scope (see _time_connection_cycle), so scope is
        # (re)fetched only after it returns.
        connection_stats = distribution(self._time_connection_cycle())
        scope = self._require_scope()
        trigger_stats = self._time_advanced_trigger(scope)
        return {
            "connection": connection_stats,
            "channel_apply": distribution(self._time_channel_apply(scope)),
            "measurement_refresh": distribution(
                _time_repeated(scope.get_all_measurement_setups, self.config.reps_standard)
            ),
            "trigger_config_apply": trigger_stats["apply"],
            "trigger_config_readback": trigger_stats["readback"],
            "unsupported_trigger_probe": self._time_unsupported_trigger_probe(scope),
            "single_acquisition": distribution(self._time_single_acquisition(scope)),
            "png_capture": distribution(self._time_png_capture(scope)),
            "csv_export": distribution(self._time_csv_export(scope)),
            "waveform_acquisition": self._time_waveform_sweep(scope),
            "not_yet_covered": list(NOT_YET_COVERED),
        }

    def _wait_until_connectable(self) -> None:
        """Block with backoff until connect()/disconnect() succeeds once.

        connect() always pays one settle gap (see its docstring), but that alone
        is not guaranteed long enough after unusually heavy prior traffic (e.g. a
        full setup reapply). Retry until the scope actually answers, so the
        subsequently-measured connection distribution reflects steady-state latency
        rather than recovery jitter.
        """
        deadline = time.monotonic() + self.config.connection_warmup_max_wait_s
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                self.connect()
                assert self.scope is not None
                self.scope.query_identity()
            except DPOError as exc:
                last_error = exc
                self.disconnect()
                continue
            else:
                self.disconnect()
                return
        raise TimeoutError(
            "Scope did not become connectable within "
            f"{self.config.connection_warmup_max_wait_s} s of warm-up retries."
        ) from last_error

    def _time_connection_cycle(self) -> list[float]:
        """Time fresh connect -> usable IDN cycles.

        Reuses connect()/disconnect() as the probe: release this capture's own held
        session first, wait until the scope is confirmed connectable again (see
        _wait_until_connectable), measure strictly sequential (never concurrent)
        connect/disconnect cycles, then reconnect for the rest of the timing
        capture. Each measured sample excludes connect()'s own unconditional settle
        sleep so this reports connect+IDN latency, not the settle gap. Use
        reps_heavy rather than reps_standard: this is a comparatively expensive,
        transport-sensitive operation.
        """
        self.disconnect()
        self._wait_until_connectable()
        samples = []
        for _ in range(self.config.reps_heavy):
            started = time.perf_counter()
            self.connect()
            assert self.scope is not None
            self.scope.query_identity()
            elapsed = time.perf_counter() - started - self.config.connection_settle_delay_s
            samples.append(max(0.0, elapsed))
            self.disconnect()
        self.connect()
        return samples

    def _time_channel_apply(self, scope: DPO4054) -> list[float]:
        channel = self.config.test_channel

        def _round_trip() -> None:
            current = scope.get_channel_configuration(channel)
            scope.configure_channel(
                ChannelConfig(
                    channel=channel,
                    display=bool_from_scope_response(current.get("display", "1")),
                    scale=current.get("scale") or None,
                    position=current.get("position") or None,
                )
            )
            scope.get_channel_configuration(channel)

        return _time_repeated(_round_trip, self.config.reps_standard)

    def _time_advanced_trigger(self, scope: DPO4054) -> dict[str, dict[str, float | int]]:
        """Time A14 configure/readback while restoring the exact pre-test setup.

        The representative PULSE/WIDTH configuration is one of the live-verified A14
        paths.  An initial untimed apply establishes that state, then apply and
        readback are measured separately.  The setup snapshot is restored even if a
        timing sample fails, so this benchmark cannot strand later acquisition tests
        behind an unlikely trigger condition.
        """
        instrument = scope.ensure_connected()
        baseline = build_scope_settings_payload(instrument)
        holdoff = scope.get_trigger_holdoff()
        config = TriggerConfig(
            trigger_type="PULSE",
            pulse_class="WIDTH",
            source=f"CH{self.config.test_channel}",
            pulse_polarity="POSITIVE",
            pulse_when="LESSTHAN",
            pulse_low_limit="8e-9",
            pulse_high_limit="12e-9",
        )
        try:
            scope.configure_trigger(config, holdoff=holdoff)
            apply_samples = _time_repeated(
                lambda: scope.configure_trigger(config, holdoff=holdoff),
                self.config.reps_standard,
            )
            readback_samples = _time_repeated(
                scope.get_trigger_configuration,
                self.config.reps_standard,
            )
        finally:
            apply_setup_string(
                instrument,
                baseline["setup"],
                wait_complete=False,
                check_error=False,
                restore_delay_s=0.5,
            )
        return {
            "apply": distribution(apply_samples),
            "readback": distribution(readback_samples),
        }

    def _time_unsupported_trigger_probe(self, scope: DPO4054) -> dict[str, float | int]:
        """Measure the known unsupported A14 probe using its dedicated timeout."""
        instrument = scope.ensure_connected()
        original_timeout = getattr(instrument, "timeout", None)
        timeout_ms = int(self.config.capability_probe_timeout_ms)
        if timeout_ms <= 0:
            raise ValueError("capability_probe_timeout_ms must be positive")

        def _probe() -> None:
            result = scope.probe_scpi_query("TRIGGER:B:EVENTS:MODE?", timeout_ms=timeout_ms)
            if result.supported:
                raise RuntimeError("Known unsupported TRIGGER:B:EVENTS:MODE? unexpectedly succeeded.")
            if not result.recovered:
                raise RuntimeError("Unsupported-trigger capability probe did not recover the session.")
            if getattr(instrument, "timeout", None) != original_timeout:
                raise RuntimeError("Capability probe did not restore the original VISA timeout.")

        stats = distribution(_time_repeated(_probe, self.config.reps_heavy))
        stats["probe_timeout_ms"] = timeout_ms
        return stats

    def _time_single_acquisition(self, scope: DPO4054) -> list[float]:
        def _cycle() -> None:
            scope.single_acquisition()
            self._wait_for_acquisition_complete(scope)

        return _time_repeated(_cycle, self.config.reps_standard)

    def _time_png_capture(self, scope: DPO4054) -> list[float]:
        target = self.config.output_dir / "_timing_scratch.png"

        def _capture() -> None:
            scope.save_image_path(target)

        samples = _time_repeated(_capture, self.config.reps_heavy)
        target.unlink(missing_ok=True)
        return samples

    def _time_csv_export(self, scope: DPO4054) -> list[float]:
        target = self.config.output_dir / "_timing_scratch.csv"
        # Force a fresh acquisition first so this measures "samples ready -> durable
        # file" against a correctly-sized completed acquisition, independent of
        # whatever ran before it.
        scope.single_acquisition()
        self._wait_for_acquisition_complete(scope)

        def _export() -> None:
            scope.save_all_channels_to_single_csv(target)

        samples = _time_repeated(_export, self.config.reps_heavy)
        target.unlink(missing_ok=True)
        return samples

    def _time_waveform_sweep(self, scope: DPO4054) -> dict[str, Any]:
        channel = self.config.test_channel
        original_record = scope.get_record_length()
        result: dict[str, Any] = {}
        try:
            seen: set[int] = set()
            for size in self.config.waveform_sizes:
                target = min(size, original_record)
                if target in seen:
                    continue
                seen.add(target)
                if scope.get_record_length() != target:
                    scope.set_record_length(target)
                # Always force a fresh acquisition before timing this size: the last
                # completed acquisition in scope memory can be smaller than the
                # currently configured record length (e.g. nothing re-armed since a
                # record-length change), which would otherwise silently time a
                # stale, wrong-sized transfer under this size's label.
                scope.single_acquisition()
                self._wait_for_acquisition_complete(scope)
                reps = (
                    self.config.reps_waveform_large
                    if target >= 1_000_000
                    else self.config.reps_heavy
                    if target >= 100_000
                    else self.config.reps_standard
                )
                actual_counts: list[int] = []

                def _timed_read() -> None:
                    actual_counts.append(scope.read_channel_waveform_data(channel).sample_count)

                samples = _time_repeated(_timed_read, reps)
                if any(count != target for count in actual_counts):
                    raise RuntimeError(
                        f"Waveform sweep at target {target} points actually transferred "
                        f"{sorted(set(actual_counts))} points; scope record length did not "
                        "match the requested sweep size."
                    )
                stats = distribution(samples)
                stats["samples_per_second"] = target / stats["p50"] if stats["p50"] > 0 else 0.0
                result[str(target)] = stats
        finally:
            if scope.get_record_length() != original_record:
                scope.set_record_length(original_record)
                scope.single_acquisition()
                self._wait_for_acquisition_complete(scope)
        return result
