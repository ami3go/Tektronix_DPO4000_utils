#!/usr/bin/env python3
"""Offline 48-hour DPO4054 soak alternating USB and Ethernet VISA sessions.

The process owns one session at a time.  It preflights both transports against
the same instrument, disconnects before every planned handoff, exercises only
public read-only driver APIs, and writes all evidence locally.  It does not need
Internet access or a controlling terminal after launch.

Example::

    python scripts/run_transport_switch_soak.py \
      --usb-resource USB0::0x0699::0x0401::C011280::INSTR \
      --ethernet-resource TCPIP0::192.168.0.5::INSTR \
      --duration-hours 48 --switch-minutes 30 \
      --output-dir qualification_reports/soak/transport-switch-48h
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import signal
import statistics
import subprocess
import sys
import threading
import time
import tracemalloc
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_hardware_soak as base  # noqa: E402


REPORT_STEM = "transport_switch_soak_report"
EVENTS_NAME = "transport_switch_events.jsonl"


def _runner_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _worktree_dirty() -> bool | None:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return bool(result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return None


@dataclass(slots=True)
class TransportSample:
    timestamp: str
    elapsed_s: float
    cycle: int
    slot: int
    transport: str
    resource: str
    identity: str
    acquisition_state: str
    trigger_state: str
    record_length: int
    bus_count: int
    reference_count: int
    cycle_duration_s: float
    rss_bytes: int | None
    python_current_bytes: int
    thread_count: int
    fd_count: int | None


@dataclass(slots=True)
class TransportFailure:
    timestamp: str
    elapsed_s: float
    cycle: int
    slot: int
    transport: str
    resource: str
    error_type: str
    message: str


def _transport_name(resource: str) -> str:
    upper = resource.strip().upper()
    if upper.startswith("USB"):
        return "usb"
    if upper.startswith("TCPIP"):
        return "ethernet"
    raise ValueError(f"Unsupported VISA transport in resource {resource!r}")


def _append_event(path: Path, event: dict[str, Any]) -> None:
    """Durably append one standard-JSON event without relying on stdout."""
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(event, sort_keys=True, allow_nan=False, separators=(",", ":"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write(encoded + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _planned_handoffs(duration_s: float, switch_s: float) -> int:
    # Slot zero starts immediately; each later slot boundary is one handoff.
    return max(0, math.ceil(duration_s / switch_s) - 1)


def _write_report(
    output_dir: Path,
    *,
    args: argparse.Namespace,
    state: dict[str, Any],
    samples: list[TransportSample],
    failures: list[TransportFailure],
    elapsed_s: float,
    run_state: str,
    status: str,
    reasons: list[str],
) -> None:
    by_transport: dict[str, list[TransportSample]] = {
        name: [sample for sample in samples if sample.transport == name]
        for name in ("usb", "ethernet")
    }
    latencies = [sample.cycle_duration_s for sample in samples]
    rss = [sample.rss_bytes for sample in samples if sample.rss_bytes is not None]
    summary = {
        "schema_version": 1,
        "kind": "dpo4054_transport_switch_soak",
        "offline_operation": True,
        "run_state": run_state,
        "status": status,
        "started_at": state["started_at"],
        "finished_at": base._utc_now(),
        "elapsed_s": elapsed_s,
        "requested_duration_hours": args.duration_hours,
        "interval_seconds": args.interval_seconds,
        "switch_minutes": args.switch_minutes,
        "resources": state["resources"],
        "baseline_identity": state["baseline_identity"],
        "preflight_identities": state["preflight_identities"],
        "final_identities": state["final_identities"],
        "baseline_setup": state["baseline_setup"],
        "commit_sha": state["commit_sha"],
        "runner_sha256": state["runner_sha256"],
        "worktree_dirty_at_start": state["worktree_dirty_at_start"],
        "cycles": len(samples) + len(failures),
        "successful_samples": len(samples),
        "samples_by_transport": {name: len(items) for name, items in by_transport.items()},
        "failures": len(failures),
        "failures_by_transport": {
            name: sum(item.transport == name for item in failures) for name in ("usb", "ethernet")
        },
        "planned_handoffs": state["planned_handoffs"],
        "completed_handoffs": state["completed_handoffs"],
        "handoff_failures": state["handoff_failures"],
        "reconnects": state["reconnects"],
        "missed_deadlines": state["missed_deadlines"],
        "cleanup_errors": state["cleanup_errors"],
        "failure_reasons": reasons,
        "cycle_latency_p50_s": _percentile(latencies, 0.50),
        "cycle_latency_p95_s": _percentile(latencies, 0.95),
        "cycle_latency_max_s": max(latencies, default=None),
        "rss_start_bytes": rss[0] if rss else None,
        "rss_end_bytes": rss[-1] if rss else None,
        "rss_peak_bytes": max(rss, default=None),
        "thread_start": samples[0].thread_count if samples else None,
        "thread_peak": max((sample.thread_count for sample in samples), default=None),
        "fd_start": next(
            (sample.fd_count for sample in samples if sample.fd_count is not None), None
        ),
        "fd_peak": max(
            (sample.fd_count for sample in samples if sample.fd_count is not None),
            default=None,
        ),
        "acceptance_limits": {
            "max_failures": args.max_failures,
            "max_handoff_failures": args.max_handoff_failures,
            "max_rss_growth_mib": args.max_rss_growth_mib,
            "max_fd_growth": args.max_fd_growth,
            "max_thread_growth": args.max_thread_growth,
            "max_cycle_latency_s": args.max_cycle_latency_s,
            "max_latency_drift_factor": args.max_latency_drift_factor,
            "max_missed_deadlines": args.max_missed_deadlines,
        },
    }
    # The append-only journal is the durable cycle-level checkpoint.  Keeping
    # RUNNING reports compact avoids rewriting an ever-growing multi-megabyte
    # sample array every minute for 48 hours; the FINAL report embeds it all.
    report_samples = [asdict(sample) for sample in samples] if run_state == "FINAL" else []
    payload = {
        "summary": summary,
        "samples": report_samples,
        "failures": [asdict(failure) for failure in failures],
    }
    base._write_atomic_text(
        output_dir / f"{REPORT_STEM}.json",
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n",
    )

    lines = [
        "# DPO4054 USB/Ethernet transport-switch soak",
        "",
        f"**Status:** {status} ({run_state})",
        f"**Elapsed:** {elapsed_s / 3600:.2f} h of {args.duration_hours:g} h requested",
        f"**USB:** `{state['resources']['usb']}`",
        f"**Ethernet:** `{state['resources']['ethernet']}`",
        "",
        "## Result",
        "",
        f"- Successful samples: {len(samples)} "
        f"(USB {len(by_transport['usb'])}, Ethernet {len(by_transport['ethernet'])})",
        f"- Failures: {len(failures)}; reconnects: {state['reconnects']}",
        f"- Completed/planned handoffs: {state['completed_handoffs']} / "
        f"{state['planned_handoffs']}; failed handoffs: {state['handoff_failures']}",
        f"- Missed deadlines: {state['missed_deadlines']}",
        f"- RSS start/end/peak MiB: {base._mib(summary['rss_start_bytes'])} / "
        f"{base._mib(summary['rss_end_bytes'])} / {base._mib(summary['rss_peak_bytes'])}",
        f"- Event journal: `{EVENTS_NAME}`",
    ]
    if reasons:
        lines += ["", "## Failure reasons", ""] + [f"- {reason}" for reason in reasons]
    if failures:
        lines += ["", "## Last cycle failures", ""] + [
            f"- {failure.elapsed_s:.1f}s {failure.transport} "
            f"{failure.error_type}: {failure.message}"
            for failure in failures[-50:]
        ]
    if state["cleanup_errors"]:
        lines += ["", "## Cleanup diagnostics", ""] + [
            f"- {error}" for error in state["cleanup_errors"]
        ]
    base._write_atomic_text(output_dir / f"{REPORT_STEM}.md", "\n".join(lines) + "\n")


def _snapshot(scope: Any) -> tuple[dict[str, Any], tuple[int, int, int]]:
    values = base._read_cycle(scope)
    setup = (
        int(values["record_length"]),
        int(values["bus_count"]),
        int(values["reference_count"]),
    )
    return values, setup


def _acquire_locks(resources: dict[str, str]) -> list[Path]:
    locks: list[Path] = []
    try:
        for resource in resources.values():
            locks.append(base._acquire_lock(resource))
    except BaseException:
        for lock in locks:
            lock.unlink(missing_ok=True)
        raise
    return locks


def _preflight(
    resources: dict[str, str],
    timeout_ms: int,
    connect: Callable[[str, int], Any],
) -> tuple[dict[str, str], str, tuple[int, int, int]]:
    identities: dict[str, str] = {}
    baseline_identity: str | None = None
    baseline_setup: tuple[int, int, int] | None = None
    for name in ("usb", "ethernet"):
        scope = None
        try:
            scope = connect(resources[name], timeout_ms)
            values, setup = _snapshot(scope)
            identity = str(values["identity"])
            if "DPO4054" not in identity.upper():
                raise RuntimeError(f"{name} resource is not a DPO4054: {identity!r}")
            if baseline_identity is not None and identity != baseline_identity:
                raise RuntimeError(
                    f"Transport identities differ: {baseline_identity!r} != {identity!r}"
                )
            if baseline_setup is not None and setup != baseline_setup:
                raise RuntimeError(
                    f"Scope setup differs between transports: {baseline_setup!r} != {setup!r}"
                )
            identities[name] = identity
            baseline_identity = identity
            baseline_setup = setup
        finally:
            cleanup = base._safe_disconnect(scope)
            if cleanup:
                raise RuntimeError(f"{name} preflight cleanup failed: {cleanup}")
    assert baseline_identity is not None and baseline_setup is not None
    return identities, baseline_identity, baseline_setup


def run_soak(
    args: argparse.Namespace,
    connect: Callable[[str, int], Any] = base._connect,
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    resources = {"usb": args.usb_resource, "ethernet": args.ethernet_resource}
    output_dir = args.output_dir
    events_path = output_dir / EVENTS_NAME
    try:
        locks = _acquire_locks(resources)
    except FileExistsError as exc:
        print(f"Transport-switch soak BLOCKED: existing resource lock ({exc})", file=sys.stderr)
        return 1

    started = clock()
    started_at = base._utc_now()
    required_s = args.duration_hours * 3600.0
    switch_s = args.switch_minutes * 60.0
    deadline = started + required_s
    state: dict[str, Any] = {
        "started_at": started_at,
        "resources": resources,
        "baseline_identity": None,
        "preflight_identities": {},
        "final_identities": {},
        "baseline_setup": None,
        "commit_sha": os.environ.get("GITHUB_SHA") or base._git_commit(),
        "runner_sha256": _runner_sha256(),
        "worktree_dirty_at_start": _worktree_dirty(),
        "planned_handoffs": _planned_handoffs(required_s, switch_s),
        "completed_handoffs": 0,
        "handoff_failures": 0,
        "reconnects": 0,
        "missed_deadlines": 0,
        "cleanup_errors": [],
    }
    samples: list[TransportSample] = []
    failures: list[TransportFailure] = []
    fatal: list[str] = []
    interrupted: list[str] = []
    scope: Any = None
    active_transport: str | None = None
    active_slot = -1
    connected_once_in_slot = False
    next_cycle = started
    next_checkpoint = started + args.checkpoint_seconds
    previous_handlers: dict[int, Any] = {}
    tracemalloc.start()

    def request_stop(signum: int, _frame: Any) -> None:
        interrupted.append(signal.Signals(signum).name)

    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        _append_event(
            events_path,
            {
                "event": "run_started",
                "timestamp": started_at,
                "resources": resources,
                "duration_hours": args.duration_hours,
                "switch_minutes": args.switch_minutes,
                "pid": os.getpid(),
            },
        )
        if threading.current_thread() is threading.main_thread():
            for signum in (signal.SIGINT, signal.SIGTERM):
                previous_handlers[signum] = signal.getsignal(signum)
                signal.signal(signum, request_stop)

        try:
            identities, identity, setup = _preflight(resources, args.timeout_ms, connect)
            state["preflight_identities"] = identities
            state["baseline_identity"] = identity
            state["baseline_setup"] = list(setup)
            _append_event(
                events_path,
                {
                    "event": "preflight_passed",
                    "timestamp": base._utc_now(),
                    "identities": identities,
                    "setup": list(setup),
                },
            )

            while clock() < deadline and not interrupted and not fatal:
                now = clock()
                slot = int((now - started) // switch_s)
                target = "usb" if slot % 2 == 0 else "ethernet"
                resource = resources[target]
                if slot != active_slot:
                    previous_transport = active_transport
                    cleanup = base._safe_disconnect(scope)
                    if cleanup:
                        state["cleanup_errors"].append(cleanup)
                    scope = None
                    active_transport = None
                    active_slot = slot
                    connected_once_in_slot = False
                    _append_event(
                        events_path,
                        {
                            "event": "handoff_started",
                            "timestamp": base._utc_now(),
                            "elapsed_s": now - started,
                            "slot": slot,
                            "from_transport": previous_transport,
                            "to_transport": target,
                        },
                    )

                cycle = len(samples) + len(failures) + 1
                cycle_started = clock()
                try:
                    if scope is None:
                        scope = connect(resource, args.timeout_ms)
                        if active_transport == target:
                            state["reconnects"] += 1
                        active_transport = target
                        if not connected_once_in_slot:
                            connected_once_in_slot = True
                            if slot > 0:
                                state["completed_handoffs"] += 1
                            _append_event(
                                events_path,
                                {
                                    "event": "handoff_completed",
                                    "timestamp": base._utc_now(),
                                    "elapsed_s": clock() - started,
                                    "slot": slot,
                                    "transport": target,
                                    "resource": resource,
                                },
                            )

                    values, current_setup = _snapshot(scope)
                    identity = str(values["identity"])
                    if identity != state["baseline_identity"]:
                        raise RuntimeError(
                            f"Instrument identity changed: {state['baseline_identity']!r} -> {identity!r}"
                        )
                    if list(current_setup) != state["baseline_setup"]:
                        raise RuntimeError(
                            f"Read-only scope setup drifted: {state['baseline_setup']!r} "
                            f"-> {list(current_setup)!r}"
                        )
                    current_py, _ = tracemalloc.get_traced_memory()
                    sample = TransportSample(
                        timestamp=base._utc_now(),
                        elapsed_s=clock() - started,
                        cycle=cycle,
                        slot=slot,
                        transport=target,
                        resource=resource,
                        identity=identity,
                        acquisition_state=str(values["acquisition_state"]),
                        trigger_state=str(values["trigger_state"]),
                        record_length=current_setup[0],
                        bus_count=current_setup[1],
                        reference_count=current_setup[2],
                        cycle_duration_s=clock() - cycle_started,
                        rss_bytes=base._rss_bytes(),
                        python_current_bytes=current_py,
                        thread_count=threading.active_count(),
                        fd_count=base._fd_count(),
                    )
                    samples.append(sample)
                    _append_event(events_path, {"event": "sample", **asdict(sample)})
                    if sample.cycle_duration_s > args.max_cycle_latency_s:
                        fatal.append(
                            f"Cycle {cycle} latency {sample.cycle_duration_s:.3f}s exceeded "
                            f"{args.max_cycle_latency_s:g}s"
                        )
                except Exception as exc:
                    failure = TransportFailure(
                        timestamp=base._utc_now(),
                        elapsed_s=clock() - started,
                        cycle=cycle,
                        slot=slot,
                        transport=target,
                        resource=resource,
                        error_type=type(exc).__name__,
                        message=str(exc),
                    )
                    failures.append(failure)
                    _append_event(events_path, {"event": "failure", **asdict(failure)})
                    if not connected_once_in_slot:
                        state["handoff_failures"] += 1
                    if "identity changed" in str(exc) or "setup drifted" in str(exc):
                        fatal.append(f"{type(exc).__name__}: {exc}")
                    cleanup = base._safe_disconnect(scope)
                    if cleanup:
                        state["cleanup_errors"].append(cleanup)
                    scope = None
                    # Preserve the target name so the next successful open is a reconnect.
                    active_transport = target

                now = clock()
                if now >= next_checkpoint:
                    _write_report(
                        output_dir,
                        args=args,
                        state=state,
                        samples=samples,
                        failures=failures,
                        elapsed_s=now - started,
                        run_state="RUNNING",
                        status="RUNNING",
                        reasons=["Qualification still running"],
                    )
                    print(
                        f"{base._utc_now()} transport soak: {(now - started) / 3600:.2f}/"
                        f"{args.duration_hours:g}h target={target} success={len(samples)} "
                        f"failures={len(failures)} handoffs={state['completed_handoffs']}/"
                        f"{state['planned_handoffs']}",
                        flush=True,
                    )
                    next_checkpoint = now + args.checkpoint_seconds

                next_cycle += args.interval_seconds
                now = clock()
                while next_cycle < now and next_cycle < deadline:
                    state["missed_deadlines"] += 1
                    next_cycle += args.interval_seconds
                remaining = min(deadline, next_cycle) - now
                if remaining > 0 and not interrupted and not fatal:
                    sleep(remaining)
        except BaseException as exc:
            fatal.append(f"Fatal run exception: {type(exc).__name__}: {exc}")
        finally:
            cleanup = base._safe_disconnect(scope)
            if cleanup:
                state["cleanup_errors"].append(cleanup)
            scope = None

            # A final live query over each transport proves both handles still open
            # independently after the last handoff.  Keep one session at a time.
            if state["baseline_identity"] is not None and not interrupted:
                for name in ("usb", "ethernet"):
                    final_scope = None
                    try:
                        final_scope = connect(resources[name], args.timeout_ms)
                        values, final_setup = _snapshot(final_scope)
                        final_identity = str(values["identity"])
                        state["final_identities"][name] = final_identity
                        if final_identity != state["baseline_identity"]:
                            fatal.append(f"Final {name} identity differs from preflight")
                        if list(final_setup) != state["baseline_setup"]:
                            fatal.append(f"Final {name} setup differs from preflight")
                    except BaseException as exc:
                        fatal.append(
                            f"Final {name} health query failed: {type(exc).__name__}: {exc}"
                        )
                    finally:
                        cleanup = base._safe_disconnect(final_scope)
                        if cleanup:
                            state["cleanup_errors"].append(cleanup)

            for signum, previous in previous_handlers.items():
                signal.signal(signum, previous)

        elapsed_s = clock() - started
        reasons = list(fatal)
        if interrupted:
            reasons.append(f"Interrupted by signal: {', '.join(interrupted)}")
        if elapsed_s < required_s:
            reasons.append("Run ended before the requested monotonic duration")
        if len(failures) > args.max_failures:
            reasons.append(f"Failures {len(failures)} exceeded maximum {args.max_failures}")
        if state["handoff_failures"] > args.max_handoff_failures:
            reasons.append(
                f"Handoff failures {state['handoff_failures']} exceeded maximum "
                f"{args.max_handoff_failures}"
            )
        if state["completed_handoffs"] < state["planned_handoffs"]:
            reasons.append(
                f"Completed only {state['completed_handoffs']} of "
                f"{state['planned_handoffs']} planned handoffs"
            )
        if state["missed_deadlines"] > args.max_missed_deadlines:
            reasons.append(
                f"Missed deadlines {state['missed_deadlines']} exceeded maximum "
                f"{args.max_missed_deadlines}"
            )
        for name in ("usb", "ethernet"):
            if not any(sample.transport == name for sample in samples):
                reasons.append(f"No successful {name} samples were recorded")
        if state["cleanup_errors"]:
            reasons.append(f"Session cleanup errors: {state['cleanup_errors']}")

        if samples:
            rss = [sample.rss_bytes for sample in samples if sample.rss_bytes is not None]
            if rss and max(rss) - rss[0] > args.max_rss_growth_mib * 1024 * 1024:
                reasons.append("Peak RSS growth exceeded limit")
            fds = [sample.fd_count for sample in samples if sample.fd_count is not None]
            if fds and max(fds) - fds[0] > args.max_fd_growth:
                reasons.append("Peak open file descriptor growth exceeded limit")
            if (
                max(sample.thread_count for sample in samples) - samples[0].thread_count
                > args.max_thread_growth
            ):
                reasons.append("Peak thread growth exceeded limit")
            if len(samples) >= 100:
                quarter = max(10, len(samples) // 4)
                early = statistics.median(item.cycle_duration_s for item in samples[:quarter])
                late = statistics.median(item.cycle_duration_s for item in samples[-quarter:])
                if late > early * args.max_latency_drift_factor and late - early > 0.5:
                    reasons.append(
                        f"Cycle latency progressively degraded: {early:.3f}s -> {late:.3f}s"
                    )

        status = "INTERRUPTED" if interrupted else ("PASS" if not reasons else "FAIL")
        _write_report(
            output_dir,
            args=args,
            state=state,
            samples=samples,
            failures=failures,
            elapsed_s=elapsed_s,
            run_state="FINAL",
            status=status,
            reasons=reasons,
        )
        _append_event(
            events_path,
            {
                "event": "run_finished",
                "timestamp": base._utc_now(),
                "elapsed_s": elapsed_s,
                "status": status,
                "reasons": reasons,
            },
        )
        print(f"Transport-switch soak {status}: {output_dir}", flush=True)
        return 0 if status == "PASS" else 1
    finally:
        for lock in locks:
            lock.unlink(missing_ok=True)


def validate_report(report_dir: Path, *, min_hours: float = 48.0) -> list[str]:
    problems: list[str] = []
    path = report_dir / f"{REPORT_STEM}.json"
    events = report_dir / EVENTS_NAME
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        summary = payload["summary"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return [f"Cannot read transport-switch report: {type(exc).__name__}: {exc}"]
    if summary.get("kind") != "dpo4054_transport_switch_soak":
        problems.append("Unexpected report kind")
    if summary.get("run_state") != "FINAL" or summary.get("status") != "PASS":
        problems.append("Report is not a finalized PASS")
    if float(summary.get("elapsed_s", -1)) < min_hours * 3600:
        problems.append(f"Elapsed duration is shorter than required {min_hours:g} h")
    if set(summary.get("samples_by_transport", {})) != {"usb", "ethernet"}:
        problems.append("Per-transport sample counts are missing")
    elif any(int(value) <= 0 for value in summary["samples_by_transport"].values()):
        problems.append("A transport has no successful samples")
    if summary.get("baseline_identity") is None or set(summary.get("final_identities", {})) != {
        "usb",
        "ethernet",
    }:
        problems.append("Preflight/final identity evidence is incomplete")
    elif any(
        identity != summary["baseline_identity"]
        for identity in summary["final_identities"].values()
    ):
        problems.append("Final transport identity differs from preflight")
    if int(summary.get("completed_handoffs", -1)) < int(summary.get("planned_handoffs", 0)):
        problems.append("Not all planned transport handoffs completed")
    if not events.is_file() or events.stat().st_size == 0:
        problems.append("Durable event journal is missing or empty")
    return problems


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--usb-resource")
    parser.add_argument("--ethernet-resource")
    parser.add_argument("--duration-hours", type=float, default=48.0)
    parser.add_argument("--switch-minutes", type=float, default=30.0)
    parser.add_argument("--interval-seconds", type=float, default=10.0)
    parser.add_argument("--checkpoint-seconds", type=float, default=60.0)
    parser.add_argument("--timeout-ms", type=int, default=20_000)
    parser.add_argument("--max-failures", type=int, default=20)
    parser.add_argument("--max-handoff-failures", type=int, default=3)
    parser.add_argument("--max-rss-growth-mib", type=float, default=256.0)
    parser.add_argument("--max-fd-growth", type=int, default=8)
    parser.add_argument("--max-thread-growth", type=int, default=4)
    parser.add_argument("--max-missed-deadlines", type=int, default=20)
    parser.add_argument("--max-cycle-latency-s", type=float, default=60.0)
    parser.add_argument("--max-latency-drift-factor", type=float, default=3.0)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("qualification_reports") / "soak" / "transport-switch-48h",
    )
    parser.add_argument("--validate-report", type=Path)
    parser.add_argument("--min-hours", type=float, default=48.0)
    args = parser.parse_args(argv)
    if args.validate_report is not None:
        if not math.isfinite(args.min_hours) or args.min_hours < 0:
            parser.error("--min-hours must be finite and non-negative")
        return args
    if not args.usb_resource or not args.ethernet_resource:
        parser.error("--usb-resource and --ethernet-resource are required")
    try:
        if _transport_name(args.usb_resource) != "usb":
            parser.error("--usb-resource must be a USB VISA resource")
        if _transport_name(args.ethernet_resource) != "ethernet":
            parser.error("--ethernet-resource must be a TCPIP VISA resource")
    except ValueError as exc:
        parser.error(str(exc))
    positive = (
        "duration_hours",
        "switch_minutes",
        "interval_seconds",
        "checkpoint_seconds",
        "max_rss_growth_mib",
        "max_cycle_latency_s",
        "max_latency_drift_factor",
    )
    for name in positive:
        value = getattr(args, name)
        if not math.isfinite(value) or value <= 0:
            parser.error(f"--{name.replace('_', '-')} must be finite and positive")
    if args.interval_seconds < 5:
        parser.error("--interval-seconds must be at least 5 seconds")
    if args.switch_minutes * 60 < args.interval_seconds:
        parser.error("--switch-minutes must be at least one sample interval")
    if args.timeout_ms <= 0:
        parser.error("--timeout-ms must be positive")
    for name in (
        "max_failures",
        "max_handoff_failures",
        "max_fd_growth",
        "max_thread_growth",
        "max_missed_deadlines",
    ):
        if getattr(args, name) < 0:
            parser.error(f"--{name.replace('_', '-')} cannot be negative")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.validate_report is not None:
        problems = validate_report(args.validate_report, min_hours=args.min_hours)
        if problems:
            print("Transport-switch soak report INVALID")
            for problem in problems:
                print(f"- {problem}")
            return 1
        print("Transport-switch soak report VALID")
        return 0
    return run_soak(args)


if __name__ == "__main__":
    raise SystemExit(main())
