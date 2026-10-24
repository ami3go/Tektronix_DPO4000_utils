#!/usr/bin/env python3
"""Long-duration DPO4000 read-only stability qualification.

This runner is intentionally separate from unit tests and the functional hardware
verifier. It keeps one DPO4054 connection alive, repeatedly exercises public
read-only APIs, reconnects only after a failed cycle, and records process/resource
observations so a 24 h or 72 h bench run can demonstrate bounded resource use.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import os
import platform
import signal
import statistics
import subprocess
import sys
import threading
import time
import tracemalloc
from tempfile import NamedTemporaryFile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dpo4000_utils import DPO4054


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _rss_bytes() -> int | None:
    """Return current process RSS using only the standard library when possible."""
    if sys.platform.startswith("linux"):
        try:
            resident_pages = int(Path("/proc/self/statm").read_text().split()[1])
            return resident_pages * int(os.sysconf("SC_PAGE_SIZE"))
        except (OSError, ValueError, IndexError):
            return None

    if os.name == "nt":
        try:
            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", ctypes.c_ulong),
                    ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(counters)
            kernel32 = ctypes.windll.kernel32
            psapi = ctypes.windll.psapi
            handle = kernel32.GetCurrentProcess()
            if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                return int(counters.WorkingSetSize)
        except (AttributeError, OSError, ValueError):
            return None

    return None


def _fd_count() -> int | None:
    if sys.platform.startswith("linux"):
        try:
            return len(list(Path("/proc/self/fd").iterdir()))
        except OSError:
            return None
    return None


@dataclass(slots=True)
class SoakSample:
    timestamp: str
    elapsed_s: float
    cycle: int
    identity: str
    acquisition_state: str
    trigger_state: str
    record_length: int
    bus_count: int
    reference_count: int
    rss_bytes: int | None
    python_current_bytes: int
    python_peak_bytes: int
    thread_count: int
    fd_count: int | None
    cycle_duration_s: float


@dataclass(slots=True)
class SoakFailure:
    timestamp: str
    elapsed_s: float
    cycle: int
    error_type: str
    message: str


def _read_cycle(scope: DPO4054) -> dict[str, Any]:
    """Exercise representative public, read-only APIs on one live session."""
    return {
        "identity": scope.query_identity(),
        "acquisition_state": scope.get_acquisition_state(),
        "trigger_state": scope.get_trigger_state(),
        "record_length": int(scope.get_record_length()),
        "bus_count": int(scope.get_bus_waveform_count()),
        "reference_count": int(scope.get_reference_waveform_count()),
    }


def _connect(resource: str, timeout_ms: int) -> DPO4054:
    scope = DPO4054(
        resource,
        auto_connect=False,
        timeout_ms=timeout_ms,
        read_termination="\n",
        write_termination="\n",
    )
    try:
        scope.connect()
    except BaseException:
        # A transport failure during connect may still leave a VISA handle open.
        _safe_disconnect(scope)
        raise
    return scope


def _safe_disconnect(scope: DPO4054 | None) -> str | None:
    if scope is None:
        return None
    try:
        scope.disconnect()
    except Exception as exc:  # cleanup diagnostic must be retained in the report.
        return f"{exc.__class__.__name__}: {exc}"
    return None


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True, timeout=3,
        )
        return result.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def _write_atomic_text(destination: Path, content: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=destination.parent,
            prefix=f".{destination.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, destination)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _lock_path(resource: str) -> Path:
    # Lock across output directories and processes on the same physical host.
    import tempfile
    digest = hashlib.sha256(resource.encode("utf-8")).hexdigest()[:24]
    return Path(tempfile.gettempdir()) / f"dpo4000-soak-{digest}.lock"


def _acquire_lock(resource: str) -> Path:
    path = _lock_path(resource)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(f"pid={os.getpid()} resource={resource} started={_utc_now()}\n")
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def _mib(value: int | None) -> str:
    return "n/a" if value is None else f"{value / (1024 * 1024):.2f}"


def _write_report(
    output_dir: Path,
    *,
    args: argparse.Namespace,
    samples: list[SoakSample],
    failures: list[SoakFailure],
    reconnects: int,
    cleanup_errors: list[str],
    started_at: str,
    elapsed_s: float,
    passed: bool,
    reasons: list[str],
    status: str | None = None,
    baseline_identity: str | None = None,
    final_identity: str | None = None,
    run_state: str = "FINAL",
    missed_deadlines: int = 0,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rss_values = [sample.rss_bytes for sample in samples if sample.rss_bytes is not None]
    py_values = [sample.python_current_bytes for sample in samples]
    fd_values = [sample.fd_count for sample in samples if sample.fd_count is not None]
    latencies = sorted(sample.cycle_duration_s for sample in samples)
    def percentile(q: float) -> float | None:
        if not latencies:
            return None
        position = (len(latencies) - 1) * q
        low = int(position)
        high = min(low + 1, len(latencies) - 1)
        return latencies[low] + (latencies[high] - latencies[low]) * (position - low)

    summary = {
        "schema_version": 2,
        "run_state": run_state,
        "status": status or ("PASS" if passed else "FAIL"),
        "started_at": started_at,
        "finished_at": _utc_now(),
        "elapsed_s": elapsed_s,
        "requested_duration_hours": args.duration_hours,
        "interval_seconds": args.interval_seconds,
        "expected_cycles": math.ceil(args.duration_hours * 3600.0 / args.interval_seconds),
        "missed_deadlines": missed_deadlines,
        "resource": args.resource,
        "baseline_identity": baseline_identity,
        "final_identity": final_identity,
        "commit_sha": os.environ.get("GITHUB_SHA") or _git_commit(),
        "acceptance_limits": {
            "max_failures": args.max_failures,
            "max_rss_growth_mib": args.max_rss_growth_mib,
            "max_python_growth_mib": args.max_python_growth_mib,
            "max_fd_growth": args.max_fd_growth,
            "max_thread_growth": args.max_thread_growth,
            "max_cycle_latency_s": args.max_cycle_latency_s,
            "max_latency_drift_factor": args.max_latency_drift_factor,
            "max_missed_deadlines": args.max_missed_deadlines,
        },
        "cycle_latency_p50_s": percentile(0.50),
        "cycle_latency_p95_s": percentile(0.95),
        "cycle_latency_p99_s": percentile(0.99) if len(samples) >= 100 else None,
        "cycle_latency_max_s": max(latencies) if latencies else None,
        "thread_start": samples[0].thread_count if samples else None,
        "thread_end": samples[-1].thread_count if samples else None,
        "thread_peak": max((sample.thread_count for sample in samples), default=None),
        "fd_peak": max((sample.fd_count for sample in samples if sample.fd_count is not None), default=None),
        "cycles": len(samples) + len(failures),
        "successful_samples": len(samples),
        "failures": len(failures),
        "reconnects": reconnects,
        "cleanup_errors": cleanup_errors,
        "failure_reasons": reasons,
        "rss_start_bytes": rss_values[0] if rss_values else None,
        "rss_end_bytes": rss_values[-1] if rss_values else None,
        "rss_peak_bytes": max(rss_values) if rss_values else None,
        "python_start_bytes": py_values[0] if py_values else None,
        "python_end_bytes": py_values[-1] if py_values else None,
        "python_peak_bytes": max(py_values) if py_values else None,
        "fd_start": fd_values[0] if fd_values else None,
        "fd_end": fd_values[-1] if fd_values else None,
        "platform": platform.platform(),
        "python": sys.version,
    }
    payload = {
        "summary": summary,
        "samples": [asdict(sample) for sample in samples],
        "failures": [asdict(failure) for failure in failures],
    }
    _write_atomic_text(
        output_dir / "soak_report.json",
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
    )

    lines = [
        "# DPO4000 hardware soak qualification",
        "",
        f"**Status:** {summary['status']}",
        f"**Started:** {started_at}",
        f"**Finished:** {summary['finished_at']}",
        f"**Elapsed:** {elapsed_s / 3600:.2f} h",
        f"**Requested:** {args.duration_hours:g} h",
        f"**Resource:** `{args.resource}`",
        "",
        "## Result",
        "",
        f"- Successful samples: {len(samples)}",
        f"- Failed cycles: {len(failures)}",
        f"- Reconnects: {reconnects}",
        f"- Expected scheduled cycles: {summary['expected_cycles']}",
        f"- Missed deadlines: {missed_deadlines}",
        f"- RSS start/end/peak MiB: {_mib(summary['rss_start_bytes'])} / "
        f"{_mib(summary['rss_end_bytes'])} / {_mib(summary['rss_peak_bytes'])}",
        f"- Python traced start/end/peak MiB: {_mib(summary['python_start_bytes'])} / "
        f"{_mib(summary['python_end_bytes'])} / {_mib(summary['python_peak_bytes'])}",
        f"- File descriptors start/end: {summary['fd_start']} / {summary['fd_end']}",
    ]
    if reasons:
        lines.extend(["", "## Failure reasons", ""])
        lines.extend(f"- {reason}" for reason in reasons)
    if failures:
        lines.extend(["", "## Cycle failures", ""])
        for failure in failures[-50:]:
            lines.append(
                f"- cycle {failure.cycle} at {failure.elapsed_s:.1f}s: "
                f"{failure.error_type}: {failure.message}"
            )
    if cleanup_errors:
        lines.extend(["", "## Cleanup diagnostics", ""])
        lines.extend(f"- {error}" for error in cleanup_errors)
    _write_atomic_text(output_dir / "soak_report.md", "\n".join(lines) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resource", required=True, help="VISA resource for the oscilloscope")
    parser.add_argument("--duration-hours", type=float, choices=(24.0, 72.0), default=24.0)
    parser.add_argument("--interval-seconds", type=float, default=10.0)
    parser.add_argument("--timeout-ms", type=int, default=20_000)
    parser.add_argument("--max-failures", type=int, default=10)
    parser.add_argument("--max-rss-growth-mib", type=float, default=256.0)
    parser.add_argument("--max-python-growth-mib", type=float, default=64.0)
    parser.add_argument("--max-fd-growth", type=int, default=8)
    parser.add_argument("--max-thread-growth", type=int, default=4)
    parser.add_argument("--max-missed-deadlines", type=int, default=10)
    parser.add_argument("--checkpoint-seconds", type=float, default=60.0)
    parser.add_argument("--max-cycle-latency-s", type=float, default=60.0)
    parser.add_argument("--max-latency-drift-factor", type=float, default=3.0)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("hardware_verification_reports") / "soak",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not math.isfinite(args.interval_seconds) or args.interval_seconds < 5.0:
        raise SystemExit("--interval-seconds must be finite and >= 5 to bound retained cycle memory")
    if args.timeout_ms <= 0:
        raise SystemExit("--timeout-ms must be positive")
    for key in (
        "max_rss_growth_mib", "max_python_growth_mib", "checkpoint_seconds",
        "max_cycle_latency_s", "max_latency_drift_factor",
    ):
        value = getattr(args, key)
        if not math.isfinite(value) or value <= 0:
            raise SystemExit(f"--{key.replace('_', '-')} must be finite and positive")
    if (
        args.max_failures < 0 or args.max_fd_growth < 0
        or args.max_thread_growth < 0 or args.max_missed_deadlines < 0
    ):
        raise SystemExit("Resource growth and failure limits cannot be negative")

    # A second qualification process must not concurrently use this resource.
    # Stale lock removal is deliberately manual after checking the bench owner.
    try:
        lock = _acquire_lock(args.resource)
    except FileExistsError:
        print(f"Soak BLOCKED: existing resource lock {_lock_path(args.resource)}", file=sys.stderr)
        return 1

    started_at = _utc_now()
    started = time.monotonic()
    required_s = args.duration_hours * 3600.0
    deadline = started + required_s
    samples: list[SoakSample] = []
    failures: list[SoakFailure] = []
    cleanup_errors: list[str] = []
    fatal_errors: list[str] = []
    interrupted: list[str] = []
    reconnects = 0
    scope: DPO4054 | None = None
    baseline_identity: str | None = None
    final_identity: str | None = None
    baseline_setup: tuple[int, int, int] | None = None
    next_checkpoint = started + args.checkpoint_seconds
    next_cycle_deadline = started
    missed_deadlines = 0
    previous_handlers: dict[int, Any] = {}
    tracemalloc.start()

    def request_stop(signum: int, _frame: Any) -> None:
        interrupted.append(signal.Signals(signum).name)

    try:
        if threading.current_thread() is threading.main_thread():
            for signum in (signal.SIGINT, signal.SIGTERM):
                previous_handlers[signum] = signal.getsignal(signum)
                signal.signal(signum, request_stop)

        try:
            while time.monotonic() < deadline and not interrupted:
                cycle = len(samples) + len(failures) + 1
                cycle_started = time.monotonic()
                try:
                    if scope is None:
                        scope = _connect(args.resource, args.timeout_ms)
                        if cycle > 1:
                            reconnects += 1
                    values = _read_cycle(scope)
                    identity = str(values["identity"])
                    setup = (
                        int(values["record_length"]),
                        int(values["bus_count"]),
                        int(values["reference_count"]),
                    )
                    if baseline_identity is None:
                        if "DPO4054" not in identity.upper():
                            raise RuntimeError(f"Not a DPO4054: {identity!r}")
                        baseline_identity = identity
                        baseline_setup = setup
                    elif identity != baseline_identity:
                        raise RuntimeError(
                            f"Instrument identity changed: {baseline_identity!r} -> {identity!r}"
                        )
                    elif setup != baseline_setup:
                        raise RuntimeError(
                            f"Read-only scope setup drifted: {baseline_setup!r} -> {setup!r}"
                        )

                    current_py, peak_py = tracemalloc.get_traced_memory()
                    samples.append(
                        SoakSample(
                            timestamp=_utc_now(),
                            elapsed_s=time.monotonic() - started,
                            cycle=cycle,
                            identity=identity,
                            acquisition_state=str(values["acquisition_state"]),
                            trigger_state=str(values["trigger_state"]),
                            record_length=setup[0],
                            bus_count=setup[1],
                            reference_count=setup[2],
                            rss_bytes=_rss_bytes(),
                            python_current_bytes=current_py,
                            python_peak_bytes=peak_py,
                            thread_count=threading.active_count(),
                            fd_count=_fd_count(),
                            cycle_duration_s=time.monotonic() - cycle_started,
                        )
                    )
                    if samples[-1].cycle_duration_s > args.max_cycle_latency_s:
                        fatal_errors.append(
                            f"Cycle {cycle} latency {samples[-1].cycle_duration_s:.3f}s "
                            f"exceeded {args.max_cycle_latency_s:g}s"
                        )
                        break
                except Exception as exc:
                    message = f"{exc.__class__.__name__}: {exc}"
                    failures.append(
                        SoakFailure(
                            timestamp=_utc_now(),
                            elapsed_s=time.monotonic() - started,
                            cycle=cycle,
                            error_type=exc.__class__.__name__,
                            message=str(exc),
                        )
                    )
                    if "identity changed" in str(exc) or "Not a DPO4054" in str(exc) or (
                        "scope setup drifted" in str(exc)
                    ):
                        fatal_errors.append(message)
                    cleanup = _safe_disconnect(scope)
                    if cleanup:
                        cleanup_errors.append(cleanup)
                    scope = None
                    if fatal_errors or len(failures) > args.max_failures:
                        break

                now = time.monotonic()
                if now >= next_checkpoint:
                    _write_report(
                        args.output_dir, args=args, samples=samples, failures=failures,
                        reconnects=reconnects, cleanup_errors=cleanup_errors,
                        started_at=started_at, elapsed_s=now - started,
                        passed=False, reasons=["Qualification still running"],
                        status="RUNNING", baseline_identity=baseline_identity,
                        run_state="RUNNING", missed_deadlines=missed_deadlines,
                    )
                    print(
                        f"{_utc_now()} soak progress: {now - started:.1f}/{required_s:.1f}s "
                        f"success={len(samples)} failures={len(failures)} "
                        f"reconnects={reconnects}",
                        flush=True,
                    )
                    next_checkpoint = now + args.checkpoint_seconds

                # Absolute monotonic scheduling: skipped periods are counted;
                # no work+sleep drift and no unbounded catch-up queue.
                next_cycle_deadline += args.interval_seconds
                now = time.monotonic()
                while next_cycle_deadline < now and next_cycle_deadline < deadline:
                    missed_deadlines += 1
                    next_cycle_deadline += args.interval_seconds
                remaining = min(deadline, next_cycle_deadline) - now
                if remaining > 0 and not interrupted:
                    time.sleep(remaining)
        except BaseException as exc:
            fatal_errors.append(f"Fatal run exception: {type(exc).__name__}: {exc}")
        finally:
            # A final live query is required, even after the duration threshold.
            # This is not counted as a normal scheduled cycle.
            try:
                if scope is None:
                    scope = _connect(args.resource, args.timeout_ms)
                values = _read_cycle(scope)
                final_identity = str(values["identity"])
                if baseline_identity is None or final_identity != baseline_identity:
                    fatal_errors.append(
                        f"Final identity mismatch: {baseline_identity!r} -> {final_identity!r}"
                    )
                final_setup = (
                    int(values["record_length"]),
                    int(values["bus_count"]),
                    int(values["reference_count"]),
                )
                if baseline_setup is None or final_setup != baseline_setup:
                    fatal_errors.append(
                        f"Final setup mismatch: {baseline_setup!r} -> {final_setup!r}"
                    )
            except BaseException as exc:
                fatal_errors.append(f"Final scope health query failed: {type(exc).__name__}: {exc}")
            finally:
                cleanup = _safe_disconnect(scope)
                if cleanup:
                    cleanup_errors.append(cleanup)
                for signum, previous in previous_handlers.items():
                    signal.signal(signum, previous)

        elapsed_s = time.monotonic() - started
        reasons = fatal_errors.copy()
        if interrupted:
            reasons.append(f"Interrupted by signal: {', '.join(interrupted)}")
        if elapsed_s < required_s:
            reasons.append("Run ended before the exact required monotonic duration")
        if len(failures) > args.max_failures:
            reasons.append(
                f"Failures {len(failures)} exceeded configured maximum {args.max_failures}"
            )
        if missed_deadlines > args.max_missed_deadlines:
            reasons.append(
                f"Missed {missed_deadlines} periodic deadlines; "
                f"limit is {args.max_missed_deadlines}"
            )
        if not samples:
            reasons.append("No successful hardware samples were recorded")
        if cleanup_errors:
            reasons.append(f"Instrument session cleanup errors: {cleanup_errors}")

        if samples:
            start_sample = samples[0]
            rss_values = [s.rss_bytes for s in samples if s.rss_bytes is not None]
            if rss_values and rss_values[0] is not None:
                growth = max(rss_values) - rss_values[0]
                if growth > args.max_rss_growth_mib * 1024 * 1024:
                    reasons.append(f"Peak RSS growth {_mib(growth)} MiB exceeds limit")
            py_growth = max(s.python_current_bytes for s in samples) - start_sample.python_current_bytes
            if py_growth > args.max_python_growth_mib * 1024 * 1024:
                reasons.append(f"Peak traced Python growth {_mib(py_growth)} MiB exceeds limit")
            fd_values = [s.fd_count for s in samples if s.fd_count is not None]
            if fd_values and max(fd_values) - fd_values[0] > args.max_fd_growth:
                reasons.append("Peak open file descriptor growth exceeded limit")
            if max(s.thread_count for s in samples) - start_sample.thread_count > args.max_thread_growth:
                reasons.append("Peak thread growth exceeded limit")
            if len(samples) >= 100:
                quarter = max(10, len(samples) // 4)
                early = statistics.median(s.cycle_duration_s for s in samples[:quarter])
                late = statistics.median(s.cycle_duration_s for s in samples[-quarter:])
                if late > early * args.max_latency_drift_factor and late - early > 0.5:
                    reasons.append(f"Latency progressively degraded: {early:.3f}s -> {late:.3f}s")

        passed = not reasons
        status = "INTERRUPTED" if interrupted else ("PASS" if passed else "FAIL")
        try:
            _write_report(
                args.output_dir, args=args, samples=samples, failures=failures,
                reconnects=reconnects, cleanup_errors=cleanup_errors,
                started_at=started_at, elapsed_s=elapsed_s,
                passed=passed, reasons=reasons, status=status,
                baseline_identity=baseline_identity, final_identity=final_identity,
                missed_deadlines=missed_deadlines,
            )
        except BaseException as exc:
            print(f"Soak evidence finalization failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        print(f"Hardware soak {status}: {args.output_dir}", flush=True)
        return 0 if passed else 1
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
