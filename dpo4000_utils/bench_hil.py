"""Probe-Comp bench HIL verification for DPO4000 Automation and Logger."""
from __future__ import annotations

import hashlib
import json
import logging
import math
import platform
import shutil
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from threading import Event
from typing import Any, Callable

from .automation import (
    ArtifactAction, AutomationProfile, AutomationRunReporter, BurstConfig,
    ConditionalCaptureConfig, ConditionalEvaluator, PeriodicImageConfig,
    PeriodicImageController, RunLimitTracker, RunLimits,
    acquire_trigger_bundle, append_measurement_row,
    load_automation_profile,
    run_burst_event, run_conditional_poll, save_automation_profile,
    save_full_record_csv,
)
from .automation.reporting import make_event_record
from .automation.retention import (
    RetentionPolicy, apply_retention_plan, plan_retention, register_retention_event,
)
from .automation.triggered import wait_for_fresh_single
from .control import ChannelConfig, MathConfig, MeasurementConfig
from .hardcopy import PNG_SIGNATURE
from .instrument import DPO4054
from .logger import (
    BoundedRecordBuffer, BufferPolicy, LoggerConfig, LoggerHealthAccumulator, LoggerWriterWorker,
    LoggerMode, LoggerOutputFormat, LoggerOutputSession, LoggerProfile,
    LoggerRetentionManager, LoggerRetentionPolicy, LoggerRunReporter,
    RotationPolicy, capture_logger_record, compute_logger_health,
    load_logger_profile, save_logger_profile, scan_dpo4log,
)
from .logger.buffering import BufferSnapshot
from .logger.models import LoggerRecord
from .settings import apply_setup_string, build_scope_settings_payload

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"


class HilSkip(RuntimeError):
    pass


@dataclass
class HilCaseResult:
    case_id: str
    title: str
    group: str
    status: str
    duration_s: float
    detail: str = ""
    error_type: str = ""
    error_message: str = ""
    traceback_path: str = ""
    artifacts: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class HilConfig:
    resource: str
    output_dir: Path
    channel: int = 1
    timeout_ms: int = 60_000
    trigger_timeout_s: float = 10.0
    waveform_points: int = 1_000
    expected_frequency_hz: float = 1_000.0
    frequency_tolerance_fraction: float = 0.35
    min_vpp_v: float = 0.5
    max_vpp_v: float = 5.0
    hardcopy: bool = True
    suite: str = "all"

    def __post_init__(self) -> None:
        self.output_dir = Path(self.output_dir)
        if self.channel not in range(1, 5):
            raise ValueError("channel must be 1..4")
        if self.waveform_points < 100:
            raise ValueError("waveform_points must be >= 100")
        if self.suite not in {"all", "automation", "logger"}:
            raise ValueError("suite must be all, automation, or logger")


class AutomationLoggerHilRunner:
    def __init__(self, config: HilConfig) -> None:
        self.config = config
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.root = config.output_dir / f"automation_logger_hil_{stamp}"
        self.root.mkdir(parents=True, exist_ok=False)
        self.artifact_root = self.root / "artifacts"
        self.error_root = self.root / "tracebacks"
        self.artifact_root.mkdir(); self.error_root.mkdir()
        self.log_path = self.root / "hil_run.log"
        self.results: list[HilCaseResult] = []
        self.scope: DPO4054 | None = None
        self.idn = ""
        self.baseline: dict[str, Any] | None = None
        self.started_at = datetime.now(timezone.utc)
        self.finished_at: datetime | None = None
        self._logger = logging.getLogger(f"dpo4000.hil.{id(self)}")
        self._logger.setLevel(logging.DEBUG); self._logger.propagate = False
        handler = logging.FileHandler(self.log_path, encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            "%(asctime)s.%(msecs)03dZ %(levelname)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S"))
        self._logger.handlers[:] = [handler]

    def _log(self, message: str, *args: Any) -> None:
        self._logger.info(message, *args)
        print(message % args if args else message, flush=True)

    @staticmethod
    def _package_version() -> str:
        try:
            return metadata.version("dpo4000-utils")
        except metadata.PackageNotFoundError:
            return "source-tree"

    @staticmethod
    def _numeric(raw: Any) -> float:
        value = float(str(raw).strip().split()[-1])
        if not math.isfinite(value) or abs(value) >= 9e36:
            raise ValueError(f"measurement unavailable: {raw!r}")
        return value

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _artifact_info(self, path: Path) -> dict[str, Any]:
        path = Path(path)
        return {"path": str(path.relative_to(self.root)), "size_bytes": path.stat().st_size,
                "sha256": self._sha256(path)}

    def _file(self, path: Path, min_bytes: int = 1) -> dict[str, Any]:
        path = Path(path)
        if not path.is_file() or path.stat().st_size < min_bytes:
            raise AssertionError(f"Missing/short artifact: {path}")
        return self._artifact_info(path)

    def _png(self, path: Path) -> dict[str, Any]:
        info = self._file(path, 64)
        with Path(path).open("rb") as handle:
            if handle.read(len(PNG_SIGNATURE)) != PNG_SIGNATURE:
                raise AssertionError(f"Not a PNG: {path}")
        return info

    def _csv(self, path: Path, min_lines: int = 2) -> dict[str, Any]:
        info = self._file(path, 10)
        with Path(path).open("r", encoding="utf-8", errors="replace") as handle:
            count = sum(1 for _ in handle)
        if count < min_lines:
            raise AssertionError(f"CSV has only {count} lines: {path}")
        info["line_count"] = count
        return info

    def _case(self, case_id: str, title: str, group: str,
              callback: Callable[[], Any]) -> None:
        self._log("CASE START %-27s %s", case_id, title)
        started = time.perf_counter()
        try:
            value = callback()
            detail, artifacts = value if isinstance(value, tuple) else (value or "", [])
        except HilSkip as exc:
            result = HilCaseResult(case_id, title, group, SKIP,
                                   time.perf_counter() - started, detail=str(exc))
        except BaseException as exc:
            tb_path = self.error_root / f"{case_id.replace('/', '_')}.txt"
            tb_path.write_text(traceback.format_exc(), encoding="utf-8")
            result = HilCaseResult(case_id, title, group, FAIL,
                time.perf_counter() - started, error_type=exc.__class__.__name__,
                error_message=str(exc), traceback_path=str(tb_path.relative_to(self.root)))
            self._logger.exception("CASE FAIL %s", case_id)
        else:
            result = HilCaseResult(case_id, title, group, PASS,
                                   time.perf_counter() - started,
                                   detail=str(detail), artifacts=list(artifacts))
        self.results.append(result)
        self._log("CASE %-5s %-27s %.3fs %s", result.status, case_id,
                  result.duration_s, result.detail or result.error_message)

    def _scope(self) -> DPO4054:
        if self.scope is None:
            raise RuntimeError("Scope not connected")
        return self.scope

    def _write_environment_snapshot(self) -> None:
        packages = {}
        for name in ("dpo4000-utils", "pyvisa", "Pillow", "PySide6"):
            try:
                packages[name] = metadata.version(name)
            except metadata.PackageNotFoundError:
                packages[name] = "not-installed"
        payload = {
            "python": sys.version,
            "executable": sys.executable,
            "platform": platform.platform(),
            "packages": packages,
            "resource": self.config.resource,
            "suite": self.config.suite,
        }
        (self.root / "environment.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def _connect_baseline(self) -> None:
        self.scope = DPO4054(
            self.config.resource, auto_connect=False, timeout_ms=self.config.timeout_ms,
            read_termination="\n", write_termination="\n",
            settings_folder=self.root / "scope_settings")
        self.scope.connect(); self.idn = self.scope.query_identity().strip()
        self._log("Connected: %s", self.idn)
        if "DPO4" not in self.idn.upper() and "MSO4" not in self.idn.upper():
            raise RuntimeError(f"Not a DPO/MSO4000-family scope: {self.idn}")
        self.baseline = build_scope_settings_payload(self.scope.ensure_connected())
        (self.root / "scope_setup_before.json").write_text(
            json.dumps(self.baseline, indent=2), encoding="utf-8")

    def _fixture(self) -> str:
        scope, ch = self._scope(), self.config.channel
        for number in range(1, 5):
            scope.configure_channel(
                ChannelConfig(
                    channel=number,
                    display=(number == ch),
                    coupling="DC" if number == ch else None,
                )
            )
        scope.set_record_length(self.config.waveform_points)
        scope.configure_edge_trigger(source=f"CH{ch}", slope="RISE", coupling="DC",
                                     mode="NORMAL", level=1.0)
        scope.add_measurement(MeasurementConfig(1, "FREQUENCY", f"CH{ch}"))
        scope.add_measurement(MeasurementConfig(2, "PK2PK", f"CH{ch}"))
        scope.continuous_acquisition()
        instrument = scope.ensure_connected()
        raw_acquisition = str(instrument.query("ACQUIRE:STATE?")).strip()
        raw_trigger = str(instrument.query("TRIGGER:STATE?")).strip()
        self._log(
            "Probe Comp preflight raw states: ACQUIRE:STATE?=%r TRIGGER:STATE?=%r",
            raw_acquisition,
            raw_trigger,
        )
        low = self.config.expected_frequency_hz * (1 - self.config.frequency_tolerance_fraction)
        high = self.config.expected_frequency_hz * (1 + self.config.frequency_tolerance_fraction)
        deadline = time.monotonic() + 5.0
        last_detail = "measurement did not settle"
        while time.monotonic() < deadline:
            try:
                freq = self._numeric(scope.read_measurement_value(1))
                vpp = self._numeric(scope.read_measurement_value(2))
                if low <= freq <= high and self.config.min_vpp_v <= vpp <= self.config.max_vpp_v:
                    return f"Probe Comp detected CH{ch}: {freq:.6g} Hz, {vpp:.6g} Vpp"
                last_detail = (
                    f"frequency={freq:g} Hz expected {low:g}..{high:g}; "
                    f"Vpp={vpp:g} V expected {self.config.min_vpp_v:g}..{self.config.max_vpp_v:g}"
                )
            except (TypeError, ValueError) as exc:
                last_detail = str(exc)
            time.sleep(0.2)
        raise AssertionError(f"Probe Comp preflight did not settle within 5 s: {last_detail}")

    def _restore(self) -> str:
        if self.scope is None or self.baseline is None:
            return "No baseline available"
        apply_setup_string(self.scope.ensure_connected(), self.baseline["setup"],
                           wait_complete=False, check_error=False, restore_delay_s=0.5)
        after = build_scope_settings_payload(self.scope.ensure_connected())
        (self.root / "scope_setup_after_restore.json").write_text(
            json.dumps(after, indent=2), encoding="utf-8")
        return ("Exact *LRN? match restored" if after.get("setup") == self.baseline.get("setup")
                else "Baseline reapplied; *LRN? differs. Compare before/after JSON")

    # Automation A1-A12 -------------------------------------------------
    def _a1(self):
        if not self.config.hardcopy: raise HilSkip("Hardcopy disabled")
        controller = PeriodicImageController(); controller.start(PeriodicImageConfig(1.0))
        token = controller.begin_event(); assert token is not None
        assert controller.begin_event() is None
        path = self.artifact_root / "automation" / "a1_periodic.png"; path.parent.mkdir(parents=True, exist_ok=True)
        self._scope().save_image_path(path); assert controller.finish_event(token, success=True)
        assert controller.statistics.succeeded == 1 and controller.statistics.skipped == 1
        controller.stop(); return "A1 capture + no-overlap passed", [self._png(path)]

    def _a2(self):
        if not self.config.hardcopy: raise HilSkip("Hardcopy disabled")
        wait = wait_for_fresh_single(self._scope(), Event(), poll_interval_s=0.1,
                                     timeout_s=self.config.trigger_timeout_s)
        if not wait.completed: raise AssertionError(f"Fresh Single failed: {asdict(wait)}")
        path = self.artifact_root / "automation" / "a2_trigger.png"
        self._scope().save_image_path(path)
        return f"A2 trigger={wait.trigger_state} elapsed={wait.elapsed_s:.3f}s", [self._png(path)]

    def _a3(self):
        if not self.config.hardcopy: raise HilSkip("Hardcopy disabled")
        root = self.artifact_root / "automation"
        result = acquire_trigger_bundle(self._scope(), Event(), poll_interval_s=0.1,
            timeout_s=self.config.trigger_timeout_s, image_path=root / "a3_bundle.png",
            csv_path=root / "a3_bundle.csv")
        if not result.artifacts_complete: raise AssertionError(f"A3 incomplete: {asdict(result)}")
        return f"A3 points={result.point_count} trigger={result.trigger_state}", [
            self._png(result.image_path), self._csv(result.csv_path)]

    def _a4(self):
        result = save_full_record_csv(self._scope(), self.artifact_root / "automation" / "a4_waveform.csv")
        if not result.success: raise AssertionError(result.error)
        return f"A4 points={result.point_count}", [self._csv(result.csv_path)]

    def _a5(self):
        path = self.artifact_root / "automation" / "a5_measurements.csv"
        started = datetime.now(timezone.utc); last = None
        for _ in range(3):
            last = append_measurement_row(self._scope(), path, (1, 2), run_started_utc=started)
            if not last.success or last.slot_errors: raise AssertionError(str(last))
            time.sleep(0.1)
        return f"A5 three rows; last={last.values}", [self._csv(path, 4)]

    def _a6(self):
        freq = self._numeric(self._scope().read_measurement_value(1))
        evaluator = ConditionalEvaluator(ConditionalCaptureConfig(
            slot=1, operator=">", threshold=max(1.0, freq * 0.5),
            consecutive_matches=1, cooldown_s=1.0))
        result = run_conditional_poll(self._scope(), evaluator, now_s=time.monotonic(),
            action=ArtifactAction.CSV,
            csv_path=str(self.artifact_root / "automation" / "a6_condition.csv"))
        if not result.captured or result.artifacts is None: raise AssertionError(str(result))
        return f"A6 fired value={result.evaluation.value:g}", [self._csv(result.artifacts.csv_path)]

    def _a7(self):
        cfg = BurstConfig(count=2, delay_s=0.0, action=ArtifactAction.CSV,
                          single_acquisition=True, poll_interval_s=0.1,
                          trigger_timeout_s=self.config.trigger_timeout_s)
        artifacts = []
        for idx in range(1, 3):
            result = run_burst_event(self._scope(), Event(), cfg,
                csv_path=self.artifact_root / "automation" / f"a7_burst_{idx:02d}.csv")
            if not result.success or result.artifacts is None: raise AssertionError(str(result))
            artifacts.append(self._csv(result.artifacts.csv_path))
        return "A7 two-event fresh-Single CSV burst passed", artifacts

    def _a8(self):
        tracker = RunLimitTracker(RunLimits(max_events=2, max_duration_s=10.0)); tracker.start(100.0)
        assert not tracker.status(1, 101.0).reached
        status = tracker.status(2, 102.0); assert status.reached
        return f"A8 exact boundary: {status.reason}"

    def _a9(self):
        root = self.artifact_root / "automation" / "a9_retention"; root.mkdir(parents=True, exist_ok=True)
        first, second = root / "old.txt", root / "new.txt"
        first.write_bytes(b"old" * 100); second.write_bytes(b"new" * 100)
        register_retention_event(root, "old", (first,), completed_utc=datetime.now(timezone.utc)); time.sleep(0.01)
        register_retention_event(root, "new", (second,), completed_utc=datetime.now(timezone.utc))
        plan = plan_retention(root, RetentionPolicy(keep_last_events=1)); result = apply_retention_plan(root, plan)
        assert result.deleted_events == 1 and not first.exists() and second.exists()
        return f"A9 reclaimed={result.reclaimed_bytes}B", [self._file(second)]

    def _a10(self):
        path = self.artifact_root / "automation" / "a10_profile.json"
        profile = AutomationProfile("Probe Comp HIL", {"mode": "Image on Trigger", "channel": self.config.channel})
        save_automation_profile(path, profile); loaded = load_automation_profile(path)
        assert loaded.name == profile.name and loaded.config == profile.config
        return "A10 profile round-trip passed", [self._file(path)]

    def _a11(self):
        before = self._scope().query_identity().strip(); self._scope().disconnect(); self._scope().connect()
        after = self._scope().query_identity().strip(); assert before == after
        return "A11 disconnect/reconnect primitive passed; physical cable fault injection not automated"

    def _a12(self):
        root = self.artifact_root / "automation" / "a12_report"
        reporter = AutomationRunReporter(root=root, mode="HIL", config={"fixture": "Probe Comp -> CH1"},
            resource=self.config.resource, idn=self.idn, package_version=self._package_version())
        now = datetime.now(timezone.utc)
        reporter.append_event(make_event_record(sequence=1, description="HIL event", cause="qualification",
            status="success", started_at=now, ended_at=datetime.now(timezone.utc)))
        summary = reporter.finalize(stop_reason="qualification complete", counters={"successful": 1, "failed": 0})
        assert json.loads(summary.read_text(encoding="utf-8"))["event_count"] == 1
        return "A12 durable event + summary passed", [self._file(reporter.event_jsonl_path),
            self._csv(reporter.event_csv_path), self._file(summary)]

    # Logger -------------------------------------------------------------
    def _logger_waveform(self):
        root = self.artifact_root / "logger" / "waveform"
        cfg = LoggerConfig(mode=LoggerMode.WAVEFORM, interval_s=0.1,
            waveform_sources=(f"CH{self.config.channel}",), point_count=self.config.waveform_points)
        output = LoggerOutputSession(root, LoggerOutputFormat.BOTH, mode=LoggerMode.WAVEFORM,
            run_metadata={"resource": self.config.resource, "idn": self.idn},
            rotation_policy=RotationPolicy(max_bytes=None, max_duration_s=None, max_records=1, daily_utc=False))
        try:
            for seq in (1, 2): output.append(capture_logger_record(self._scope(), cfg, seq))
        finally: output.close()
        assert output.records_written == 2 and output.rotation_count >= 1
        artifacts = []
        for path in output.paths:
            artifacts.append(self._file(path))
            if path.suffix == ".csv": self._csv(path)
            if path.suffix == ".dpo4log":
                scan = scan_dpo4log(path)
                if not scan.clean_end or scan.truncated or scan.record_count < 1: raise AssertionError(str(scan))
        return f"Waveform BOTH format records=2 rotations={output.rotation_count}", artifacts

    def _logger_measurements(self):
        root = self.artifact_root / "logger" / "measurements"
        cfg = LoggerConfig(mode=LoggerMode.MEASUREMENTS, interval_s=0.1,
            waveform_sources=(), measurement_slots=(1, 2))
        output = LoggerOutputSession(root, LoggerOutputFormat.BOTH, mode=LoggerMode.MEASUREMENTS,
            measurement_slots=(1, 2), run_metadata={"resource": self.config.resource, "idn": self.idn})
        last = None
        try:
            for seq in (1, 2, 3):
                last = capture_logger_record(self._scope(), cfg, seq); output.append(last)
        finally: output.close()
        assert last is not None and not last.measurement_errors
        return f"Measurement Logger records=3 last={dict(last.measurements)}", [self._file(p) for p in output.paths]

    def _logger_mixed(self):
        root = self.artifact_root / "logger" / "mixed"
        cfg = LoggerConfig(mode=LoggerMode.MIXED, interval_s=0.1,
            waveform_sources=(f"CH{self.config.channel}",), measurement_slots=(1, 2),
            point_count=self.config.waveform_points)
        record = capture_logger_record(self._scope(), cfg, 1, cancel_event=Event())
        if bool(record.metadata.get("partial")): raise AssertionError(str(record.metadata))
        output = LoggerOutputSession(root, LoggerOutputFormat.BOTH, mode=LoggerMode.MIXED,
            measurement_slots=(1, 2), run_metadata={"resource": self.config.resource, "idn": self.idn})
        try: output.append(record)
        finally: output.close()
        assert len(record.waveforms) == 1 and len(record.measurements) == 2
        return f"Mixed fresh-Single trigger={record.metadata.get('trigger_state')}", [self._file(p) for p in output.paths]

    def _logger_math(self):
        self._scope().configure_math(MathConfig(display=True, define=f"CH{self.config.channel}"))
        cfg = LoggerConfig(mode=LoggerMode.WAVEFORM, interval_s=0.1, waveform_sources=("MATH",),
                           point_count=self.config.waveform_points)
        record = capture_logger_record(self._scope(), cfg, 1)
        assert len(record.waveforms) == 1 and record.waveforms[0].source == "MATH"
        return f"MATH Logger captured {record.waveforms[0].sample_count} points"

    def _logger_bus(self):
        if not self._scope().supports_decoded_bus_events():
            raise HilSkip("Decoded BUS extraction is unqualified; Probe Comp -> CH1 cannot qualify serial decode")
        raise HilSkip("BUS decode requires real serial-bus stimulus, not Probe Comp")

    def _logger_buffer_health(self):
        policy = BufferPolicy(max_records=2, max_bytes=10_000_000, stop_after_overflows=2)
        buffer = BoundedRecordBuffer(policy); now = datetime.now(timezone.utc).isoformat()
        r1, r2, r3 = (LoggerRecord(sequence=i, captured_utc=now) for i in (1, 2, 3))
        assert buffer.try_put(r1) and buffer.try_put(r2) and not buffer.try_put(r3)
        assert buffer.pop_left() is r1
        capture = LoggerHealthAccumulator(); capture.note_capture(r2, 0.01)
        snapshot = BufferSnapshot(queued_records=buffer.queued_records, queued_bytes=buffer.queued_bytes,
            written_records=1, bytes_written=100, total_write_s=0.01)
        health = compute_logger_health(capture.snapshot(), snapshot, elapsed_s=1.0, buffer_policy=policy)
        assert buffer.dropped_records == 1

        # Exercise the same dedicated writer-thread architecture used by the GUI.
        root = self.artifact_root / "logger" / "writer_thread"
        worker = LoggerWriterWorker(
            lambda: LoggerOutputSession(root, LoggerOutputFormat.BINARY, mode=LoggerMode.MEASUREMENTS,
                measurement_slots=(1, 2), run_metadata={"source": "HIL writer thread"}),
            BufferPolicy(max_records=4, max_bytes=10_000_000, stop_after_overflows=2))
        worker.start()
        cfg = LoggerConfig(mode=LoggerMode.MEASUREMENTS, interval_s=0.1, waveform_sources=(),
                           measurement_slots=(1, 2))
        for seq in (10, 11):
            assert worker.try_enqueue(capture_logger_record(self._scope(), cfg, seq))
        worker.request_stop(drain=True); assert worker.wait(10.0)
        ws = worker.snapshot()
        if ws.error or ws.written_records != 2:
            raise AssertionError(f"Logger writer thread failed: {ws}")
        paths = sorted(root.glob("*.dpo4log"))
        if not paths:
            raise AssertionError("Logger writer thread produced no DPO4LOG artifact")
        artifacts = []
        for path in paths:
            scan = scan_dpo4log(path)
            if not scan.clean_end or scan.truncated or scan.record_count < 1:
                raise AssertionError(f"Invalid writer-thread DPO4LOG {path}: {scan}")
            artifacts.append(self._file(path))
        return (
            f"Buffer overflow + health + writer thread passed; written={ws.written_records}; "
            f"effective_rate={health.effective_records_per_s:.3f}/s",
            artifacts,
        )

    def _logger_recovery(self):
        before = self._scope().query_identity().strip()
        self._scope().disconnect(); self._scope().connect()
        after = self._scope().query_identity().strip()
        assert before == after
        return "Logger recovery reconnect primitive passed; physical transport-fault injection is intentionally not automatic"

    def _logger_profile(self):
        root = self.artifact_root / "logger" / "profile"; root.mkdir(parents=True, exist_ok=True)
        path = root / "probe_comp.json"
        profile = LoggerProfile(name="Probe Comp", config={
            "mode": LoggerMode.WAVEFORM.value, "interval_s": 1.0,
            "waveform_sources": [f"CH{self.config.channel}"], "measurement_slots": [], "bus_slots": [],
            "encoding": "RIBINARY", "sample_width": 2, "point_count": self.config.waveform_points,
            "output_format": LoggerOutputFormat.BOTH.value, "output_root": str(root / "output"),
            "keep_session": True,
            "rotation": {"max_bytes": None, "max_duration_s": None, "max_records": 10, "daily_utc": False},
            "retention": {"keep_last_events": 5, "max_bytes": None, "max_age_s": None, "min_free_bytes": None},
            "recovery": {"enabled": True, "max_retries": 2, "retry_delay_s": 1.0, "max_consecutive_failures": 5},
            "buffer": {"max_records": 8, "max_bytes": 1048576, "stop_after_overflows": 5}})
        save_logger_profile(path, profile); loaded = load_logger_profile(path); assert loaded.name == profile.name
        return "Logger profile round-trip passed", [self._file(path)]

    def _logger_retention(self):
        root = self.artifact_root / "logger" / "retention"; root.mkdir(parents=True, exist_ok=True)
        first, second = root / "segment1.dpo4log", root / "segment2.dpo4log"
        first.write_bytes(b"one" * 100); second.write_bytes(b"two" * 100)
        manager = LoggerRetentionManager(root, LoggerRetentionPolicy(
            keep_last_events=1, max_bytes=None, max_age_s=None, min_free_bytes=None))
        manager.register_closed_segment((first,)); time.sleep(0.01); manager.register_closed_segment((second,))
        plan, result = manager.apply(); assert plan.satisfied and result.deleted_events == 1
        assert not first.exists() and second.exists()
        return f"Logger retention reclaimed={result.reclaimed_bytes}B", [self._file(second)]

    def _logger_report(self):
        root = self.artifact_root / "logger" / "report"
        reporter = LoggerRunReporter(root=root, config={"fixture": "Probe Comp -> CH1"},
            package_version=self._package_version(), resource=self.config.resource, idn=self.idn)
        reporter.append_event("start", details={"suite": "HIL"})
        checkpoint = reporter.checkpoint({"records_captured": 1, "records_written": 1}, reason="qualification")
        summary = reporter.finalize(stop_reason="qualification complete",
            state={"records_captured": 1, "records_written": 1})
        return "Logger event/checkpoint/final report passed", [self._file(reporter.event_jsonl_path),
            self._csv(reporter.event_csv_path), self._file(checkpoint), self._file(summary)]

    def _automation_cases(self) -> None:
        for cid, title, fn in [
            ("A1-periodic-image", "Periodic Image", self._a1),
            ("A2-image-on-trigger", "Image on Trigger", self._a2),
            ("A3-image-csv-trigger", "Image + CSV on Trigger", self._a3),
            ("A4-timed-waveform", "Timed waveform logging", self._a4),
            ("A5-measurement-log", "Measurement logger", self._a5),
            ("A6-conditional", "Conditional capture", self._a6),
            ("A7-burst", "Burst capture", self._a7),
            ("A8-limits", "Run duration/count limits", self._a8),
            ("A9-retention", "Automation retention", self._a9),
            ("A10-profiles", "Automation profiles", self._a10),
            ("A11-reconnect", "Reconnect primitive", self._a11),
            ("A12-report", "Automation report", self._a12)]:
            self._case(cid, title, "automation", fn)

    def _logger_cases(self) -> None:
        for cid, title, fn in [
            ("logger-waveform", "Waveform CSV + DPO4LOG + rotation", self._logger_waveform),
            ("logger-measurements", "Measurement CSV + DPO4LOG", self._logger_measurements),
            ("logger-mixed", "Fresh-Single mixed records", self._logger_mixed),
            ("logger-math", "MATH waveform source", self._logger_math),
            ("logger-bus", "BUS decoded events", self._logger_bus),
            ("logger-buffer-health", "Bounded buffer + health + writer thread", self._logger_buffer_health),
            ("logger-recovery", "Logger reconnect/recovery primitive", self._logger_recovery),
            ("logger-profile", "Logger profile", self._logger_profile),
            ("logger-retention", "Logger retention", self._logger_retention),
            ("logger-report", "Logger report/checkpoint", self._logger_report)]:
            self._case(cid, title, "logger", fn)

    def _write_report(self) -> None:
        self.finished_at = datetime.now(timezone.utc)
        counts = {s: sum(r.status == s for r in self.results) for s in (PASS, FAIL, SKIP)}
        payload = {
            "schema_version": 1,
            "status": FAIL if counts[FAIL] else PASS,
            "started_utc": self.started_at.isoformat(),
            "finished_utc": self.finished_at.isoformat(),
            "elapsed_s": (self.finished_at - self.started_at).total_seconds(),
            "resource": self.config.resource, "idn": self.idn,
            "package_version": self._package_version(), "python": sys.version,
            "platform": platform.platform(),
            "config": {**asdict(self.config), "output_dir": str(self.config.output_dir)},
            "counts": counts, "results": [asdict(r) for r in self.results]}
        (self.root / "hil_report.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
        lines = ["# DPO4000 Automation + Logger Probe Comp HIL", "",
            f"**Status:** {payload['status']}", f"**Resource:** `{self.config.resource}`",
            f"**IDN:** `{self.idn}`", f"**PASS/FAIL/SKIP:** {counts[PASS]} / {counts[FAIL]} / {counts[SKIP]}",
            "", "| Case | Group | Status | Duration | Detail |", "|---|---|---|---:|---|"]
        for r in self.results:
            detail = (r.detail or f"{r.error_type}: {r.error_message}").replace("|", "\\|").replace("\n", " ")
            lines.append(f"| `{r.case_id}` | {r.group} | **{r.status}** | {r.duration_s:.3f}s | {detail} |")
        lines += ["", "## Debug bundle", "", "- `hil_run.log`: chronological trace",
            "- `tracebacks/`: full Python traceback for each failed case",
            "- `hil_report.json`: machine-readable case details",
            "- `environment.json`: Python/package/platform snapshot",
            "- `scope_setup_before.json` / `scope_setup_after_restore.json`: scope-state evidence",
            "- `artifacts/`: generated PNG/CSV/DPO4LOG/profile/report evidence",
            "- Upload the diagnostic ZIP path printed by the runner for debugging.", ""]
        (self.root / "hil_report.md").write_text("\n".join(lines), encoding="utf-8")

    def _zip(self) -> Path:
        return Path(shutil.make_archive(str(self.root.parent / f"{self.root.name}_diagnostic_bundle"), "zip",
                                        root_dir=self.root, base_dir="."))

    def run(self) -> tuple[int, Path]:
        self._log("DPO4000 Automation + Logger HIL starting")
        self._log("Resource=%s suite=%s waveform_points=%d", self.config.resource,
                  self.config.suite, self.config.waveform_points)
        try:
            self._write_environment_snapshot()
            self._connect_baseline()
            self._case("fixture-probe-comp", "Probe Comp signal preflight", "fixture", self._fixture)
            if self.results[-1].status == PASS:
                if self.config.suite in {"all", "automation"}: self._automation_cases()
                if self.config.suite in {"all", "logger"}: self._logger_cases()
            else:
                self._log("Fixture preflight failed; hardware-dependent cases not run")
        except BaseException as exc:
            path = self.error_root / "runner_fatal.txt"; path.write_text(traceback.format_exc(), encoding="utf-8")
            self.results.append(HilCaseResult("runner-fatal", "Runner initialization", "runner", FAIL, 0.0,
                error_type=exc.__class__.__name__, error_message=str(exc),
                traceback_path=str(path.relative_to(self.root))))
            self._logger.exception("Fatal HIL runner error")
        finally:
            if self.scope is not None and self.baseline is not None:
                self._case("scope-restore", "Restore original scope setup", "fixture", self._restore)
            if self.scope is not None:
                try: self.scope.disconnect()
                except Exception: self._logger.exception("Cleanup disconnect failed")
            self._write_report(); zip_path = self._zip()
            failed = any(r.status == FAIL for r in self.results)
            self._log("HIL %s report=%s", "FAIL" if failed else "PASS", self.root)
            self._log("Upload bundle: %s", zip_path)
        return (1 if any(r.status == FAIL for r in self.results) else 0), zip_path


__all__ = ["AutomationLoggerHilRunner", "HilCaseResult", "HilConfig", "HilSkip"]
