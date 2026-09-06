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
import json
import os
import platform
import sys
import threading
import time
import tracemalloc
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
    scope.connect()
    return scope


def _safe_disconnect(scope: DPO4054 | None) -> str | None:
    if scope is None:
        return None
    try:
        scope.disconnect()
    except Exception as exc:  # cleanup diagnostic must be retained in the report.
        return f"{exc.__class__.__name__}: {exc}"
    return None


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
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rss_values = [sample.rss_bytes for sample in samples if sample.rss_bytes is not None]
    py_values = [sample.python_current_bytes for sample in samples]
    fd_values = [sample.fd_count for sample in samples if sample.fd_count is not None]
    summary = {
        "status": "PASS" if passed else "FAIL",
        "started_at": started_at,
        "finished_at": _utc_now(),
        "elapsed_s": elapsed_s,
        "requested_duration_hours": args.duration_hours,
        "interval_seconds": args.interval_seconds,
        "resource": args.resource,
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
    (output_dir / "soak_report.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
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
    (output_dir / "soak_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("hardware_verification_reports") / "soak",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.interval_seconds <= 0:
        raise SystemExit("--interval-seconds must be positive")
    if args.timeout_ms <= 0:
        raise SystemExit("--timeout-ms must be positive")

    started_at = _utc_now()
    started = time.monotonic()
    deadline = started + args.duration_hours * 3600.0
    samples: list[SoakSample] = []
    failures: list[SoakFailure] = []
    cleanup_errors: list[str] = []
    reconnects = 0
    scope: DPO4054 | None = None
    tracemalloc.start()

    try:
        while time.monotonic() < deadline:
            cycle = len(samples) + len(failures) + 1
            cycle_started = time.monotonic()
            try:
                if scope is None:
                    scope = _connect(args.resource, args.timeout_ms)
                    if cycle > 1:
                        reconnects += 1
                values = _read_cycle(scope)
                current_py, peak_py = tracemalloc.get_traced_memory()
                samples.append(
                    SoakSample(
                        timestamp=_utc_now(),
                        elapsed_s=time.monotonic() - started,
                        cycle=cycle,
                        identity=str(values["identity"]),
                        acquisition_state=str(values["acquisition_state"]),
                        trigger_state=str(values["trigger_state"]),
                        record_length=int(values["record_length"]),
                        bus_count=int(values["bus_count"]),
                        reference_count=int(values["reference_count"]),
                        rss_bytes=_rss_bytes(),
                        python_current_bytes=current_py,
                        python_peak_bytes=peak_py,
                        thread_count=threading.active_count(),
                        fd_count=_fd_count(),
                        cycle_duration_s=time.monotonic() - cycle_started,
                    )
                )
            except Exception as exc:
                failures.append(
                    SoakFailure(
                        timestamp=_utc_now(),
                        elapsed_s=time.monotonic() - started,
                        cycle=cycle,
                        error_type=exc.__class__.__name__,
                        message=str(exc),
                    )
                )
                cleanup = _safe_disconnect(scope)
                if cleanup:
                    cleanup_errors.append(cleanup)
                scope = None
                if len(failures) > args.max_failures:
                    break

            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(min(args.interval_seconds, remaining))
    finally:
        cleanup = _safe_disconnect(scope)
        if cleanup:
            cleanup_errors.append(cleanup)

    elapsed_s = time.monotonic() - started
    reasons: list[str] = []
    if elapsed_s + max(args.interval_seconds, 1.0) < args.duration_hours * 3600.0:
        reasons.append("Run ended before the requested soak duration completed.")
    if len(failures) > args.max_failures:
        reasons.append(
            f"Failures {len(failures)} exceeded configured maximum {args.max_failures}."
        )
    if not samples:
        reasons.append("No successful hardware samples were recorded.")

    if samples:
        rss_values = [sample.rss_bytes for sample in samples if sample.rss_bytes is not None]
        if len(rss_values) >= 2:
            rss_growth = rss_values[-1] - rss_values[0]
            rss_limit = int(args.max_rss_growth_mib * 1024 * 1024)
            if rss_growth > rss_limit:
                reasons.append(
                    f"RSS grew by {_mib(rss_growth)} MiB, above "
                    f"{args.max_rss_growth_mib:.2f} MiB limit."
                )

        py_growth = samples[-1].python_current_bytes - samples[0].python_current_bytes
        py_limit = int(args.max_python_growth_mib * 1024 * 1024)
        if py_growth > py_limit:
            reasons.append(
                f"Python traced memory grew by {_mib(py_growth)} MiB, above "
                f"{args.max_python_growth_mib:.2f} MiB limit."
            )

        fd_values = [sample.fd_count for sample in samples if sample.fd_count is not None]
        if len(fd_values) >= 2 and fd_values[-1] - fd_values[0] > args.max_fd_growth:
            reasons.append(
                f"File descriptor count grew by {fd_values[-1] - fd_values[0]}, above "
                f"configured limit {args.max_fd_growth}."
            )

    passed = not reasons
    _write_report(
        args.output_dir,
        args=args,
        samples=samples,
        failures=failures,
        reconnects=reconnects,
        cleanup_errors=cleanup_errors,
        started_at=started_at,
        elapsed_s=elapsed_s,
        passed=passed,
        reasons=reasons,
    )
    print(f"Hardware soak {'PASS' if passed else 'FAIL'}: {args.output_dir}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
