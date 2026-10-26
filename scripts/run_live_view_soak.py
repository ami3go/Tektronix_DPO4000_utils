#!/usr/bin/env python3
"""Long-duration DPO4054 four-channel Live View soak (default 12 h), fully offline.

Streams complete sequential CH1..CH4 groups through the same Qt-independent path the
Live View uses (``LiveStreamEngine`` + ``capture_group`` + ``PreambleCache``) on one
retained connection, and records throughput, group latency, skew, resource use and
failures. Every ``--lifecycle-minutes`` it pauses/resumes and stops/restarts the
stream to expose leaks in the lifecycle. At the end it restores the ``DATA:*``
transfer registers (the only scope state the read path writes) and proves the full
``SET?`` setup is unchanged.

Needs only the Python standard library and this repository: no internet, no GUI.
Run it on an exclusively reserved scope; it takes the same per-resource lock as
``run_hardware_soak.py`` so the two cannot overlap.

    python scripts/run_live_view_soak.py --resource USB0::0x0699::0x0401::C011280::INSTR \
        --output-dir qualification_reports/soak/live-view-12h
    python scripts/run_live_view_soak.py --validate-report qualification_reports/soak/live-view-12h \
        --min-hours 12 --expected-commit "$(git rev-parse HEAD)"

A run shorter than 12 h is allowed for smoke tests but is reported as not qualifying.
This soak is headless: a stall shows up as a group exceeding --max-group-latency-s, not
as a Qt UI heartbeat gap (those are covered by the offscreen GUI heartbeat test).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import re
import signal
import statistics
import sys
import threading
import time
import tracemalloc
from array import array
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_hardware_soak as base  # noqa: E402  (shared helpers: RSS, lock, atomic write)
from dpo4000_utils.live_stream import (  # noqa: E402
    LiveStreamEngine, StreamConfig, capture_group,
)
from dpo4000_utils.waveform import PreambleCache  # noqa: E402

QUALIFYING_HOURS = 12.0
REPORT_NAME = "live_soak_report"
_DATA_QUERIES = {
    "SOURCE": "DATA:SOURCE?", "START": "DATA:START?", "STOP": "DATA:STOP?",
    "WIDTH": "DATA:WIDTH?", "ENCDG": "DATA:ENCDG?",
}
_MAX_DURATIONS = 1_000_000  # bounded run-wide latency store (~8 MB)
POLL_S = 0.05  # scheduler poll step (tests raise it to speed up simulated runs)


@dataclass(slots=True)
class LiveSoakSample:
    timestamp: str
    elapsed_s: float
    window_s: float
    groups: int
    failures: int
    groups_per_s: float
    group_p50_s: float | None
    group_p95_s: float | None
    group_p99_s: float | None
    group_max_s: float | None
    skew_max_s: float
    deadlines_skipped: int
    engine_state: str
    lifecycle_ops: int
    rss_bytes: int | None
    python_current_bytes: int | None
    thread_count: int
    fd_count: int | None


@dataclass(slots=True)
class LiveSoakFailure:
    timestamp: str
    elapsed_s: float
    error_type: str
    message: str


def _percentile(sorted_values: list[float], q: float) -> float | None:
    if not sorted_values:
        return None
    position = (len(sorted_values) - 1) * q
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    return sorted_values[low] + (sorted_values[high] - sorted_values[low]) * (position - low)


def _parse_sources(text: str) -> tuple[str, ...]:
    sources = tuple(part.strip().upper() for part in text.split(",") if part.strip())
    if not 1 <= len(sources) <= 4 or len(set(sources)) != len(sources) or any(
        s not in {"CH1", "CH2", "CH3", "CH4"} for s in sources
    ):
        raise argparse.ArgumentTypeError("--sources must be 1..4 unique channels from CH1..CH4")
    return sources


def _data_registers(session: Any) -> dict[str, str]:
    values = {key: str(session.query(query)).strip().strip('"')
              for key, query in _DATA_QUERIES.items()}
    for key, value in values.items():
        if not re.fullmatch(r"[A-Za-z0-9]+", value):
            raise RuntimeError(f"Unsafe or missing DATA:{key} response {value!r}")
    return values


def _restore_data_registers(session: Any, initial: dict[str, str]) -> bool:
    session.write(f"DATA:SOURCE {initial['SOURCE']}")
    session.write("DATA:START 1")
    session.write(f"DATA:STOP {initial['STOP']}")
    session.write(f"DATA:START {initial['START']}")
    session.write(f"DATA:WIDTH {initial['WIDTH']}")
    session.write(f"DATA:ENCDG {initial['ENCDG']}")
    return _data_registers(session) == initial


def _set_snapshot(session: Any) -> str:
    return str(session.query("SET?")).strip().replace(";", "\n") + "\n"


def _setup_signature(group: Any) -> tuple:
    """Read-only identity of what the scope is sending: drift means someone changed it."""
    return tuple(
        (f.waveform.source, f.waveform.sample_count, f.waveform.preamble.x_increment,
         f.waveform.preamble.y_multiplier, f.waveform.preamble.y_unit)
        for f in group.frames
    )


def _write_report(output_dir: Path, *, args: argparse.Namespace, state: dict[str, Any],
                  samples: list[LiveSoakSample], failures: list[LiveSoakFailure],
                  run_state: str, status: str, reasons: list[str], elapsed_s: float) -> None:
    durations = sorted(state["durations"])
    rss = [s.rss_bytes for s in samples if s.rss_bytes is not None]
    summary = {
        "schema_version": 1, "kind": "dpo4054_live_view_soak",
        "run_state": run_state, "status": status,
        "started_at": state["started_at"], "finished_at": base._utc_now(),
        "elapsed_s": elapsed_s, "requested_duration_hours": args.duration_hours,
        "qualifying_duration_met": args.duration_hours >= QUALIFYING_HOURS,
        "resource": args.resource, "sources": list(state["sources"]),
        "target_hz": args.target_hz, "commit_sha": os.environ.get("GITHUB_SHA") or base._git_commit(),
        "baseline_identity": state["baseline_identity"], "final_identity": state["final_identity"],
        "groups_completed": state["groups"], "group_failures": len(failures),
        "reconnects": state["reconnects"], "lifecycle_ops": state["lifecycle_ops"],
        "deadlines_skipped": state["skipped"],
        "group_latency_p50_s": _percentile(durations, 0.50),
        "group_latency_p95_s": _percentile(durations, 0.95),
        "group_latency_p99_s": _percentile(durations, 0.99),
        "group_latency_max_s": durations[-1] if durations else None,
        "skew_max_s": state["skew_max"],
        "rss_start_bytes": rss[0] if rss else None, "rss_end_bytes": rss[-1] if rss else None,
        "rss_peak_bytes": max(rss) if rss else None,
        "thread_start": samples[0].thread_count if samples else None,
        "thread_peak": max((s.thread_count for s in samples), default=None),
        "fd_start": next((s.fd_count for s in samples if s.fd_count is not None), None),
        "fd_peak": max((s.fd_count for s in samples if s.fd_count is not None), default=None),
        "data_registers_restored": state["data_restored"],
        "set_unchanged": state["set_unchanged"], "set_diff": state["set_diff"],
        "cleanup_errors": state["cleanup_errors"], "failure_reasons": reasons,
        "acceptance_limits": {
            "max_failures": args.max_failures, "max_rss_growth_mib": args.max_rss_growth_mib,
            "max_fd_growth": args.max_fd_growth, "max_thread_growth": args.max_thread_growth,
            "max_group_latency_s": args.max_group_latency_s,
            "max_latency_drift_factor": args.max_latency_drift_factor,
        },
        "platform": platform.platform(), "python": sys.version,
    }
    payload = {"summary": summary, "samples": [asdict(s) for s in samples],
               "failures": [asdict(f) for f in failures]}
    base._write_atomic_text(output_dir / f"{REPORT_NAME}.json",
                            json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n")
    p50 = summary["group_latency_p50_s"]
    p99 = summary["group_latency_p99_s"]
    lines = [
        "# DPO4054 four-channel Live View soak", "",
        f"**Status:** {status} ({run_state})", f"**Elapsed:** {elapsed_s / 3600:.2f} h of "
        f"{args.duration_hours:g} h requested"
        + ("" if summary["qualifying_duration_met"] else "  — **below the 12 h qualifying duration**"),
        f"**Resource:** `{args.resource}`  **Channels:** {', '.join(state['sources'])}", "",
        "## Result", "",
        f"- Complete groups: {state['groups']}  |  failed groups: {len(failures)}  |  reconnects: {state['reconnects']}",
        f"- Group latency p50/p99/max s: {p50 if p50 is None else round(p50, 3)} / "
        f"{p99 if p99 is None else round(p99, 3)} / {summary['group_latency_max_s'] if durations else None}",
        f"- Max first-to-last channel skew: {state['skew_max'] * 1000:.0f} ms  |  skipped deadlines: {state['skipped']}",
        f"- Lifecycle pause/stop cycles: {state['lifecycle_ops']}",
        f"- RSS start/end/peak MiB: {base._mib(summary['rss_start_bytes'])} / "
        f"{base._mib(summary['rss_end_bytes'])} / {base._mib(summary['rss_peak_bytes'])}",
        f"- DATA registers restored: {state['data_restored']}  |  full SET? unchanged: {state['set_unchanged']}",
    ]
    if reasons:
        lines += ["", "## Failure reasons", ""] + [f"- {r}" for r in reasons]
    if failures:
        lines += ["", "## Last group failures", ""] + [
            f"- {f.elapsed_s:.1f}s {f.error_type}: {f.message}" for f in failures[-30:]]
    base._write_atomic_text(output_dir / f"{REPORT_NAME}.md", "\n".join(lines) + "\n")


def run_soak(
    args: argparse.Namespace,
    connect: Callable[[str, int], Any],
    *,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> int:
    """Run the soak against ``connect(resource, timeout_ms)``; returns a process exit code."""
    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    try:
        lock = base._acquire_lock(args.resource)
    except FileExistsError:
        print(f"Soak BLOCKED: existing resource lock {base._lock_path(args.resource)}", file=sys.stderr)
        return 1

    sources = tuple(args.sources)
    config = StreamConfig(sources=sources, point_count=None, target_hz=args.target_hz)
    state: dict[str, Any] = {
        "started_at": base._utc_now(), "sources": sources, "durations": array("d"),
        "groups": 0, "reconnects": 0, "lifecycle_ops": 0, "skipped": 0,
        "skew_max": 0.0, "baseline_identity": None, "final_identity": None,
        "data_restored": None, "set_unchanged": None, "set_diff": [], "cleanup_errors": [],
    }
    samples: list[LiveSoakSample] = []
    failures: list[LiveSoakFailure] = []
    fatal: list[str] = []
    interrupted: list[str] = []
    previous_handlers: dict[int, Any] = {}
    engine = LiveStreamEngine(clock=clock)
    cache = PreambleCache()
    scope: Any = None
    initial_data: dict[str, str] | None = None
    set_before: str | None = None
    baseline_signature: tuple | None = None
    started = clock()
    deadline = started + args.duration_hours * 3600.0
    window_start = started
    window_durations: list[float] = []
    window_failures = window_groups = 0
    window_skew = 0.0
    skipped_at_window_start = 0
    window_p50s: list[float] = []
    next_checkpoint = started + args.checkpoint_seconds
    next_lifecycle = started + args.lifecycle_minutes * 60.0 if args.lifecycle_minutes else None
    lifecycle_toggle = False
    if args.tracemalloc:
        tracemalloc.start()

    def request_stop(signum: int, _frame: Any) -> None:
        interrupted.append(signal.Signals(signum).name)

    def skipped_now() -> int:
        return state["skipped"] + engine.stats().deadlines_skipped

    def take_sample(now: float) -> None:
        nonlocal window_start, window_durations, window_failures, window_groups
        nonlocal window_skew, skipped_at_window_start
        span = max(now - window_start, 1e-9)
        ordered = sorted(window_durations)
        p50 = _percentile(ordered, 0.50)
        if p50 is not None:
            window_p50s.append(p50)
        current_py = tracemalloc.get_traced_memory()[0] if args.tracemalloc else None
        total_skipped = skipped_now()
        samples.append(LiveSoakSample(
            timestamp=base._utc_now(), elapsed_s=now - started, window_s=span,
            groups=window_groups, failures=window_failures, groups_per_s=window_groups / span,
            group_p50_s=p50, group_p95_s=_percentile(ordered, 0.95),
            group_p99_s=_percentile(ordered, 0.99), group_max_s=ordered[-1] if ordered else None,
            skew_max_s=window_skew, deadlines_skipped=total_skipped - skipped_at_window_start,
            engine_state=engine.state.value, lifecycle_ops=state["lifecycle_ops"],
            rss_bytes=base._rss_bytes(), python_current_bytes=current_py,
            thread_count=threading.active_count(), fd_count=base._fd_count(),
        ))
        skipped_at_window_start = total_skipped
        window_start, window_durations = now, []
        window_failures = window_groups = 0
        window_skew = 0.0

    def checkpoint(now: float) -> None:
        _write_report(out, args=args, state=state, samples=samples, failures=failures,
                      run_state="RUNNING", status="RUNNING",
                      reasons=["Qualification still running"], elapsed_s=now - started)
        print(f"{base._utc_now()} live soak: {now - started:.0f}/{args.duration_hours * 3600:.0f}s "
              f"groups={state['groups']} failures={len(failures)} reconnects={state['reconnects']}",
              flush=True)

    try:
        if threading.current_thread() is threading.main_thread():
            for signum in (signal.SIGINT, signal.SIGTERM):
                previous_handlers[signum] = signal.getsignal(signum)
                signal.signal(signum, request_stop)
        try:
            scope = connect(args.resource, args.timeout_ms)
            identity = str(scope.query_identity())
            if "DPO4054" not in identity.upper():
                raise RuntimeError(f"Not a DPO4054: {identity!r}")
            state["baseline_identity"] = identity
            session = scope.ensure_connected()
            shown = {f"CH{n}" for n in scope._enabled_channel_numbers()}
            hidden = [s for s in sources if s not in shown]
            if hidden:
                raise RuntimeError(f"{', '.join(hidden)} not displayed on the scope; enable them first")
            initial_data = _data_registers(session)
            set_before = _set_snapshot(session)
            base._write_atomic_text(out / "set_before.txt", set_before)
            engine.start(config)
        except BaseException as exc:
            fatal.append(f"Preflight failed: {type(exc).__name__}: {exc}")

        while not fatal and clock() < deadline and not interrupted:
            now = clock()
            if next_lifecycle is not None and now >= next_lifecycle:
                if lifecycle_toggle:
                    state["skipped"] += engine.stats().deadlines_skipped
                    engine.stop()
                    cache = PreambleCache()
                    engine.start(config)
                else:
                    engine.pause()
                    sleep(0.2)
                    engine.resume()
                lifecycle_toggle = not lifecycle_toggle
                state["lifecycle_ops"] += 1
                next_lifecycle = now + args.lifecycle_minutes * 60.0
            if now - window_start >= args.sample_seconds:
                take_sample(now)
            if now >= next_checkpoint:
                checkpoint(now)
                next_checkpoint = now + args.checkpoint_seconds

            if scope is None:  # reconnect after a failed group
                try:
                    scope = connect(args.resource, args.timeout_ms)
                    state["reconnects"] += 1
                    cache = PreambleCache()
                    state["skipped"] += engine.stats().deadlines_skipped
                    engine.stop()
                    engine.start(config)
                except Exception as exc:
                    failures.append(LiveSoakFailure(base._utc_now(), now - started,
                                                    type(exc).__name__, f"reconnect: {exc}"))
                    window_failures += 1
                    if len(failures) > args.max_failures:
                        break
                    sleep(min(5.0, args.sample_seconds))
                continue

            delay = engine.due_in()
            if delay is None:
                sleep(POLL_S)
                continue
            if delay:
                sleep(min(delay, POLL_S))
                continue
            token = engine.begin_due()
            if token is None:
                continue
            began = clock()
            try:
                group = capture_group(scope, config, *token, preamble_cache=cache, clock=clock)
                took = clock() - began
                signature = _setup_signature(group)
                if baseline_signature is None:
                    baseline_signature = signature
                elif signature != baseline_signature:
                    fatal.append(f"Read-only scope setup drifted during the soak: "
                                 f"{baseline_signature!r} -> {signature!r}")
                if not engine.complete(token, group):
                    raise RuntimeError("Engine discarded a complete group unexpectedly")
                engine.take_latest()
                state["groups"] += 1
                window_groups += 1
                window_durations.append(took)
                if len(state["durations"]) < _MAX_DURATIONS:
                    state["durations"].append(took)
                window_skew = max(window_skew, group.channel_skew_s)
                state["skew_max"] = max(state["skew_max"], group.channel_skew_s)
                if took > args.max_group_latency_s:
                    fatal.append(f"Group latency {took:.1f}s exceeded {args.max_group_latency_s:g}s")
            except Exception as exc:
                engine.fail(token, exc)
                failures.append(LiveSoakFailure(base._utc_now(), clock() - started,
                                                type(exc).__name__, str(exc)))
                window_failures += 1
                cleanup = base._safe_disconnect(scope)
                if cleanup:
                    state["cleanup_errors"].append(cleanup)
                scope = None
                if len(failures) > args.max_failures:
                    break
        # fall through to final verification
    except BaseException as exc:
        fatal.append(f"Fatal run exception: {type(exc).__name__}: {exc}")
    finally:
        try:
            state["skipped"] += engine.stats().deadlines_skipped
            engine.stop()
            if scope is None and state["baseline_identity"] is not None:
                scope = connect(args.resource, args.timeout_ms)
            if scope is not None and state["baseline_identity"] is not None:
                state["final_identity"] = str(scope.query_identity())
                if state["final_identity"] != state["baseline_identity"]:
                    fatal.append(f"Final identity mismatch: {state['baseline_identity']!r} -> "
                                 f"{state['final_identity']!r}")
                session = scope.ensure_connected()
                if initial_data is not None:
                    state["data_restored"] = _restore_data_registers(session, initial_data)
                    if not state["data_restored"]:
                        fatal.append("DATA:* registers did not match the initial snapshot after restore")
                if set_before is not None:
                    set_after = _set_snapshot(session)
                    base._write_atomic_text(out / "set_after.txt", set_after)
                    state["set_unchanged"] = set_after == set_before
                    if not state["set_unchanged"]:
                        before, after = set_before.splitlines(), set_after.splitlines()
                        state["set_diff"] = [f"{a} -> {b}" for a, b in zip(before, after) if a != b][:20]
                        if len(before) != len(after):
                            state["set_diff"].append(f"line count {len(before)} -> {len(after)}")
                        fatal.append("Full SET? setup differs from the start of the soak")
        except BaseException as exc:
            fatal.append(f"Final verification failed: {type(exc).__name__}: {exc}")
        finally:
            cleanup = base._safe_disconnect(scope)
            if cleanup:
                state["cleanup_errors"].append(cleanup)
            for signum, previous in previous_handlers.items():
                signal.signal(signum, previous)
            if args.tracemalloc:
                tracemalloc.stop()

    try:
        now = clock()
        if now - window_start > 1.0 or not samples:
            take_sample(now)
        elapsed = now - started
        reasons = list(fatal)
        if interrupted:
            reasons.append(f"Interrupted by signal: {', '.join(interrupted)}")
        if elapsed < args.duration_hours * 3600.0 and not interrupted and not fatal:
            reasons.append("Run ended before the requested duration")
        if len(failures) > args.max_failures:
            reasons.append(f"Group failures {len(failures)} exceeded maximum {args.max_failures}")
        if state["groups"] == 0:
            reasons.append("No complete groups were acquired")
        if state["cleanup_errors"]:
            reasons.append(f"Session cleanup errors: {state['cleanup_errors']}")
        rss = [s.rss_bytes for s in samples if s.rss_bytes is not None]
        if rss and max(rss) - rss[0] > args.max_rss_growth_mib * 1024 * 1024:
            reasons.append(f"Peak RSS growth {base._mib(max(rss) - rss[0])} MiB exceeds limit")
        fds = [s.fd_count for s in samples if s.fd_count is not None]
        if fds and max(fds) - fds[0] > args.max_fd_growth:
            reasons.append("File descriptor growth exceeded limit")
        if samples and max(s.thread_count for s in samples) - samples[0].thread_count > args.max_thread_growth:
            reasons.append("Thread growth exceeded limit")
        if len(window_p50s) >= 8:
            quarter = max(2, len(window_p50s) // 4)
            early = statistics.median(window_p50s[:quarter])
            late = statistics.median(window_p50s[-quarter:])
            if late > early * args.max_latency_drift_factor and late - early > 0.1:
                reasons.append(f"Group latency progressively degraded: {early:.3f}s -> {late:.3f}s")
        status = "INTERRUPTED" if interrupted else ("PASS" if not reasons else "FAIL")
        _write_report(out, args=args, state=state, samples=samples, failures=failures,
                      run_state="FINAL", status=status, reasons=reasons, elapsed_s=elapsed)
        print(f"Live View soak {status}: {out}", flush=True)
        return 0 if status == "PASS" else 1
    except BaseException as exc:
        print(f"Soak evidence finalization failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        lock.unlink(missing_ok=True)


def validate_report(directory: Path, *, min_hours: float, expected_commit: str | None) -> list[str]:
    """Offline structural check of a finished soak; returns a list of problems (empty = OK)."""
    path = directory / f"{REPORT_NAME}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        summary = data["summary"]
    except (OSError, ValueError, KeyError) as exc:
        return [f"Cannot read {path}: {exc}"]
    problems: list[str] = []
    if summary.get("kind") != "dpo4054_live_view_soak":
        problems.append("Not a Live View soak report")
    if summary.get("run_state") != "FINAL":
        problems.append(f"run_state is {summary.get('run_state')!r}, not FINAL")
    if summary.get("status") != "PASS":
        problems.append(f"status is {summary.get('status')!r}: {summary.get('failure_reasons')}")
    if float(summary.get("elapsed_s", 0)) < min_hours * 3600.0:
        problems.append(f"elapsed {float(summary.get('elapsed_s', 0)) / 3600:.2f} h < required {min_hours:g} h")
    if float(summary.get("requested_duration_hours", 0)) < min_hours:
        problems.append("requested duration below the required minimum")
    if expected_commit and summary.get("commit_sha") != expected_commit:
        problems.append(f"commit {summary.get('commit_sha')!r} != expected {expected_commit!r}")
    if not summary.get("groups_completed"):
        problems.append("no complete groups")
    if summary.get("data_registers_restored") is not True:
        problems.append("DATA registers were not verified restored")
    if summary.get("set_unchanged") is not True:
        problems.append("full SET? was not verified unchanged")
    if not summary.get("baseline_identity") or summary.get("baseline_identity") != summary.get("final_identity"):
        problems.append("instrument identity missing or changed")
    for name in ("set_before.txt", "set_after.txt"):
        if not (directory / name).is_file():
            problems.append(f"missing {name}")
    return problems


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--resource", help="VISA resource for the oscilloscope")
    p.add_argument("--duration-hours", type=float, default=QUALIFYING_HOURS)
    p.add_argument("--sources", type=_parse_sources, default=("CH1", "CH2", "CH3", "CH4"))
    p.add_argument("--target-hz", type=float, default=5.0, help="requested group rate (cap)")
    p.add_argument("--timeout-ms", type=int, default=20_000)
    p.add_argument("--sample-seconds", type=float, default=30.0, help="metrics window")
    p.add_argument("--checkpoint-seconds", type=float, default=60.0)
    p.add_argument("--lifecycle-minutes", type=float, default=30.0,
                   help="pause/resume then stop/restart alternately; 0 disables")
    p.add_argument("--max-failures", type=int, default=10)
    p.add_argument("--max-rss-growth-mib", type=float, default=256.0)
    p.add_argument("--max-fd-growth", type=int, default=8)
    p.add_argument("--max-thread-growth", type=int, default=4)
    p.add_argument("--max-group-latency-s", type=float, default=30.0)
    p.add_argument("--max-latency-drift-factor", type=float, default=2.0)
    p.add_argument("--tracemalloc", action="store_true",
                   help="also record Python-allocated bytes (slows decimation noticeably)")
    p.add_argument("--output-dir", type=Path, default=Path("qualification_reports/soak/live-view"))
    p.add_argument("--validate-report", type=Path, metavar="DIR",
                   help="validate a finished soak directory offline and exit")
    p.add_argument("--min-hours", type=float, default=QUALIFYING_HOURS)
    p.add_argument("--expected-commit")
    args = p.parse_args(argv)
    if args.validate_report is None:
        if not args.resource:
            p.error("--resource is required")
        for key in ("duration_hours", "target_hz", "sample_seconds", "checkpoint_seconds",
                    "max_rss_growth_mib", "max_group_latency_s", "max_latency_drift_factor"):
            value = getattr(args, key)
            if not math.isfinite(value) or value <= 0:
                p.error(f"--{key.replace('_', '-')} must be finite and positive")
        if args.sample_seconds < 1.0:
            p.error("--sample-seconds must be >= 1 to bound the retained samples")
        if args.timeout_ms <= 0 or args.lifecycle_minutes < 0 or min(
                args.max_failures, args.max_fd_growth, args.max_thread_growth) < 0:
            p.error("timeouts must be positive and limits non-negative")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.validate_report is not None:
        problems = validate_report(args.validate_report, min_hours=args.min_hours,
                                   expected_commit=args.expected_commit)
        for problem in problems:
            print(f"INVALID: {problem}")
        print("Live View soak report VALID" if not problems else "Live View soak report INVALID")
        return 1 if problems else 0
    if args.duration_hours < QUALIFYING_HOURS:
        print(f"NOTE: {args.duration_hours:g} h is below the {QUALIFYING_HOURS:g} h qualifying "
              "duration; this run is a smoke test.", file=sys.stderr)
    return run_soak(args, base._connect)


if __name__ == "__main__":
    raise SystemExit(main())
