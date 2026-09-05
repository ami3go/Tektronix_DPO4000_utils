"""Opt-in GUI hardware-in-the-loop tests for Automation and Logger.

Bench topologies:

1. Probe-comp: Tektronix CH1 connected to the oscilloscope PROBE COMP output.
2. Pico-AWG: Tektronix CH1 connected to the PicoScope 2206B signal-generator output.

The module intentionally imports PySide6 and PicoSDK only after the corresponding
environment gates are enabled so ordinary CI can collect and skip these tests.
"""

from __future__ import annotations

import ctypes
import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from dpo4000_utils import DPO4054
from dpo4000_utils.automation import ArtifactAction, parse_measurement_value
from dpo4000_utils.automation.triggered import wait_for_fresh_single
from dpo4000_utils.connection import visaResourceAddr
from dpo4000_utils.control import AcquisitionConfig, ChannelConfig, MathConfig, MeasurementConfig
from dpo4000_utils.logger.models import LoggerMode, LoggerOutputFormat, LoggerRecord, LoggerState


_TRUE_VALUES = {"1", "true", "yes", "on"}
AUTOMATION_PAGE_INDEX = 5
LOGGER_PAGE_INDEX = 6
FILE_PAGE_INDEX = 7
AUTOMATION_MODES = (
    "Periodic Image",
    "Image on Trigger",
    "Image + CSV on Trigger",
    "Timed Waveform Logging",
    "Measurement Logger",
    "Conditional Capture",
    "Burst Capture",
)


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE_VALUES


def _require_env(name: str, reason: str) -> None:
    if not _enabled(name):
        pytest.skip(f"Set {name}=1 {reason}.")


def _resource() -> str:
    return os.getenv("DPO4000_RESOURCE", visaResourceAddr).strip()


@pytest.fixture(scope="session")
def gui_hil_resource() -> str:
    _require_env("DPO4000_HARDWARE", "to enable real oscilloscope access")
    _require_env("DPO4000_GUI_HIL", "to enable Automation/Logger GUI HIL")
    _require_env(
        "DPO4000_ENABLE_WRITE_TESTS",
        "because GUI HIL changes CH1, trigger, acquisition, MATH and measurement setup",
    )
    resource = _resource()
    if not resource:
        pytest.skip("DPO4000_RESOURCE is empty.")
    return resource


@pytest.fixture(scope="session")
def scope(gui_hil_resource: str) -> Iterator[DPO4054]:
    instrument = DPO4054(gui_hil_resource, auto_connect=False)
    instrument.connect()
    if instrument.scope is not None:
        instrument.scope.timeout = int(os.getenv("DPO4000_TIMEOUT_MS", "20000"))
    try:
        yield instrument
    finally:
        try:
            instrument.continuous_acquisition()
        finally:
            instrument.disconnect()


@pytest.fixture(scope="session")
def qt_app(gui_hil_resource: str):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication
    except ModuleNotFoundError as exc:
        pytest.skip(f"PySide6 is required for GUI HIL: {exc}")
    app = QApplication.instance()
    if app is None:
        app = QApplication(["dpo4000-gui-hil"])
    return app


def _pump(app: Any, seconds: float = 0.05) -> None:
    deadline = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()


def _wait_until(app: Any, predicate, timeout_s: float, description: str) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    app.processEvents()
    assert predicate(), f"Timed out waiting for {description}"


def _configure_measurements(instrument: DPO4054) -> None:
    types = ("PK2PK", "FREQUENCY", "RMS", "MEAN", "MAXIMUM", "MINIMUM", "PERIOD", "AMPLITUDE")
    for slot, measurement_type in enumerate(types, start=1):
        instrument.add_measurement(
            MeasurementConfig(slot=slot, measurement_type=measurement_type, source1="CH1")
        )


def _configure_scope_for_signal(
    instrument: DPO4054,
    *,
    scale_v_per_div: float,
    trigger_level_v: float,
) -> None:
    for channel in range(1, 5):
        instrument.configure_channel(
            ChannelConfig(
                channel=channel,
                display=channel == 1,
                scale=scale_v_per_div if channel == 1 else None,
                position=0,
                offset=0,
                coupling="DC" if channel == 1 else None,
                probe_gain=1 if channel == 1 else None,
            )
        )
    instrument.configure_acquisition(AcquisitionConfig(mode="SAMPLE", record_length="1k"))
    instrument.configure_edge_trigger(
        source="CH1", slope="RISE", coupling="DC", mode="NORMAL", level=trigger_level_v
    )
    instrument.configure_math(MathConfig(display=True, define="CH1", scale=scale_v_per_div))
    _configure_measurements(instrument)
    instrument.continuous_acquisition()
    time.sleep(0.4)


def _assert_fresh_trigger(instrument: DPO4054, *, timeout_s: float = 5.0) -> None:
    result = wait_for_fresh_single(instrument, None, poll_interval_s=0.1, timeout_s=timeout_s)
    assert result.completed and result.observed_fresh_state, (
        "CH1 did not complete a fresh Single acquisition. Check the cable from "
        "PROBE COMP/Pico AWG to CH1, CH1 scale and trigger level. "
        f"Last trigger state={result.trigger_state!r}."
    )
    instrument.continuous_acquisition()


@pytest.fixture
def gui_window(qt_app: Any, scope: DPO4054, tmp_path: Path):
    from dpo4000_utils.gui_qt.production_hardening_window import QtScopeWindow

    window = QtScopeWindow()
    for index in (AUTOMATION_PAGE_INDEX, LOGGER_PAGE_INDEX, FILE_PAGE_INDEX):
        window._ensure_control_page_built(index)
    window.output_folder.setText(str(tmp_path))
    window._connection_ok = True
    window._last_idn = scope.query_identity()
    messages: list[tuple[str, str, bool]] = []

    def direct_action(description: str, callback):
        started = time.monotonic()
        result = callback(scope)
        elapsed = max(0.0, time.monotonic() - started)
        if isinstance(result, LoggerRecord):
            window._logger_health.note_capture(result, elapsed)
        window._last_action = f"Completed: {description}"
        return result

    def record_message(title: str, text: str, *, error: bool = False):
        messages.append((str(title), str(text), bool(error)))

    window._run_action = direct_action
    window._message = record_message
    window._hil_messages = messages
    window.show()
    _pump(qt_app)
    try:
        yield window
    finally:
        try:
            window.stop_automation()
        except Exception:
            pass
        try:
            window.stop_logger()
        except Exception:
            pass
        _pump(qt_app, 0.1)
        window.close()
        _pump(qt_app, 0.05)


@pytest.fixture
def probe_comp_scope(scope: DPO4054) -> DPO4054:
    _require_env(
        "DPO4000_PROBE_COMP_HIL",
        "when CH1 is physically connected to the oscilloscope PROBE COMP output",
    )
    scale = float(os.getenv("DPO4000_PROBE_COMP_SCALE_VDIV", "1.0"))
    trigger = float(os.getenv("DPO4000_PROBE_COMP_TRIGGER_V", "0.5"))
    _configure_scope_for_signal(scope, scale_v_per_div=scale, trigger_level_v=trigger)
    _assert_fresh_trigger(scope)
    return scope


def _iter_prefixed_controls(window: Any, prefix: str):
    from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QLineEdit, QRadioButton, QSpinBox

    types = (QCheckBox, QRadioButton, QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit)
    seen: set[int] = set()
    for name, value in vars(window).items():
        if not name.startswith(prefix):
            continue
        candidates: list[tuple[str, Any]] = []
        if isinstance(value, types):
            candidates.append((name, value))
        elif isinstance(value, dict):
            for key, child in value.items():
                if isinstance(child, types):
                    candidates.append((f"{name}[{key!r}]", child))
        for qualified, control in candidates:
            if id(control) in seen:
                continue
            seen.add(id(control))
            yield qualified, control


def _exercise_control(name: str, control: Any) -> None:
    from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QLineEdit, QRadioButton, QSpinBox

    if isinstance(control, (QCheckBox, QRadioButton)):
        original = control.isChecked()
        if name == "automation_retention_auto":
            assert not control.isEnabled()
            return
        control.setChecked(not original)
        assert control.isChecked() is (not original)
        control.setChecked(original)
        return
    if isinstance(control, QComboBox):
        original = control.currentIndex()
        assert control.count() > 0, f"{name} has no choices"
        for index in range(control.count()):
            control.setCurrentIndex(index)
            assert control.currentIndex() == index
        control.setCurrentIndex(original)
        return
    if isinstance(control, QSpinBox):
        original = control.value()
        midpoint = (control.minimum() + control.maximum()) // 2
        for value in (control.minimum(), midpoint, control.maximum()):
            control.setValue(int(value))
            assert control.minimum() <= control.value() <= control.maximum()
        control.setValue(original)
        return
    if isinstance(control, QDoubleSpinBox):
        original = control.value()
        midpoint = (control.minimum() + control.maximum()) / 2.0
        for value in (control.minimum(), midpoint, control.maximum()):
            control.setValue(float(value))
            assert control.minimum() <= control.value() <= control.maximum()
        control.setValue(original)
        return
    if isinstance(control, QLineEdit):
        original = control.text()
        control.setText("HIL_OPTION_TEST")
        assert control.text() == "HIL_OPTION_TEST"
        control.setText(original)


@pytest.mark.hardware
@pytest.mark.gui_hil
def test_gui_all_automation_and_logger_option_widgets_round_trip(
    gui_window: Any, probe_comp_scope: DPO4054
) -> None:
    """Traverse all value-bearing Automation/Logger options and profile them."""
    automation_controls = list(_iter_prefixed_controls(gui_window, "automation_"))
    logger_controls = list(_iter_prefixed_controls(gui_window, "logger_"))
    assert len(automation_controls) >= 20
    assert len(logger_controls) >= 20
    for name, control in automation_controls:
        _exercise_control(name, control)
    for name, control in logger_controls:
        _exercise_control(name, control)
    automation_profile = gui_window._collect_automation_profile_config()
    gui_window._apply_automation_profile_config(automation_profile)
    logger_profile = gui_window._collect_logger_profile_config()
    normalized = gui_window._preflight_logger_profile_ui(logger_profile)
    gui_window._apply_logger_profile_config(normalized)


def _select_only(mapping: dict[Any, Any], selected: set[Any]) -> None:
    for key, checkbox in mapping.items():
        checkbox.setChecked(key in selected)


def _set_automation_mode(window: Any, mode: str) -> None:
    index = window.automation_mode_combo.findText(mode)
    assert index >= 0, f"Automation mode missing from final GUI: {mode}"
    window.automation_mode_combo.setCurrentIndex(index)


def _configure_one_shot_automation(window: Any, mode: str, measured_pk2pk: float) -> None:
    _set_automation_mode(window, mode)
    window.automation_interval_value.setValue(1.0)
    window.automation_interval_unit.setCurrentText("seconds")
    window.automation_trigger_poll.setValue(0.1)
    window.automation_trigger_rearm.setChecked(False)
    if mode == "Measurement Logger":
        _select_only(window.automation_measurement_slots, {1, 2, 3, 4})
    if mode == "Conditional Capture":
        window.automation_condition_slot.setCurrentIndex(0)
        index = window.automation_condition_operator.findData(">")
        assert index >= 0
        window.automation_condition_operator.setCurrentIndex(index)
        window.automation_condition_threshold.setValue(max(0.0, measured_pk2pk * 0.5))
        window.automation_condition_debounce.setValue(1)
        window.automation_condition_cooldown.setValue(1.0)
        window.automation_condition_action.setCurrentText(ArtifactAction.IMAGE_CSV.value)
    if mode == "Burst Capture":
        window.automation_burst_count.setValue(1)
        window.automation_burst_delay.setValue(0.0)
        window.automation_burst_action.setCurrentText(ArtifactAction.IMAGE_CSV.value)
        window.automation_burst_single.setChecked(True)
        window.automation_burst_poll.setValue(0.1)


def _automation_expected_suffixes(mode: str) -> set[str]:
    if mode in {"Periodic Image", "Image on Trigger"}:
        return {".png"}
    if mode in {"Timed Waveform Logging", "Measurement Logger"}:
        return {".csv"}
    return {".png", ".csv"}


@pytest.mark.hardware
@pytest.mark.gui_hil
@pytest.mark.probe_comp
@pytest.mark.parametrize("mode", AUTOMATION_MODES)
def test_probe_comp_all_automation_modes_create_expected_artifacts(
    mode: str,
    gui_window: Any,
    probe_comp_scope: DPO4054,
    qt_app: Any,
    tmp_path: Path,
) -> None:
    measured_pk2pk = parse_measurement_value(probe_comp_scope.read_measurement_value(1))
    assert measured_pk2pk > 0.05
    _configure_one_shot_automation(gui_window, mode, measured_pk2pk)
    before = {path.resolve() for path in tmp_path.rglob("*") if path.is_file()}
    gui_window.run_automation_once()
    expected = _automation_expected_suffixes(mode)

    def artifacts_ready() -> bool:
        after = {path.resolve() for path in tmp_path.rglob("*") if path.is_file()}
        new = [path for path in after - before if path.suffix.lower() in expected]
        return expected.issubset({path.suffix.lower() for path in new})

    _wait_until(qt_app, artifacts_ready, 20.0, f"{mode} artifact(s)")
    assert not [message for message in gui_window._hil_messages if message[2]]


@pytest.mark.hardware
@pytest.mark.gui_hil
@pytest.mark.probe_comp
def test_probe_comp_automation_pause_resume_and_limits(
    gui_window: Any, probe_comp_scope: DPO4054, qt_app: Any
) -> None:
    _set_automation_mode(gui_window, "Periodic Image")
    gui_window.automation_interval_value.setValue(1.0)
    gui_window.automation_interval_unit.setCurrentText("seconds")
    gui_window.automation_limit_count_enabled.setChecked(True)
    gui_window.automation_limit_count.setValue(2)
    gui_window.start_automation()
    _wait_until(
        qt_app,
        lambda: gui_window._automation_controller.state.value == "Running",
        3.0,
        "Automation Running",
    )
    gui_window.pause_resume_automation()
    assert gui_window._automation_controller.state.value == "Paused"
    gui_window.pause_resume_automation()
    assert gui_window._automation_controller.state.value == "Running"
    gui_window.stop_automation()
    assert not gui_window._automation_any_active()


def _configure_logger_common(window: Any) -> None:
    window.logger_interval.setValue(0.1)
    window.logger_rotate_size_enabled.setChecked(False)
    window.logger_rotate_duration_enabled.setChecked(False)
    window.logger_rotate_count_enabled.setChecked(False)
    window.logger_rotate_daily_utc.setChecked(False)
    window.logger_keep_segments_enabled.setChecked(False)
    window.logger_max_storage_enabled.setChecked(False)
    window.logger_max_age_enabled.setChecked(False)
    window.logger_min_free_enabled.setChecked(False)
    window.logger_reconnect_enabled.setChecked(True)
    window.logger_reconnect_retries.setValue(1)
    window.logger_reconnect_delay.setValue(0.1)
    window.logger_reconnect_max_failures.setValue(3)
    window.logger_queue_records.setValue(4)
    window.logger_queue_memory_mb.setValue(64)
    window.logger_queue_stop_overflows.setValue(3)


def _configure_logger_case(
    window: Any, mode: LoggerMode, output: LoggerOutputFormat, source: str
) -> None:
    _configure_logger_common(window)
    window.logger_mode_combo.setCurrentText(mode.value)
    window.logger_output_format.setCurrentText(output.value)
    _select_only(window.logger_channel_checks, {"CH1"} if source == "CH1" else set())
    math_check = getattr(window, "logger_math_check", None)
    if math_check is not None:
        math_check.setChecked(source == "MATH")
    measurements = set(range(1, 9)) if mode in {LoggerMode.MEASUREMENTS, LoggerMode.MIXED} else set()
    _select_only(window.logger_measurement_checks, measurements)
    _select_only(window.logger_bus_checks, set())


LOGGER_CASES = (
    (LoggerMode.WAVEFORM, LoggerOutputFormat.CSV, "CH1"),
    (LoggerMode.WAVEFORM, LoggerOutputFormat.BINARY, "CH1"),
    (LoggerMode.WAVEFORM, LoggerOutputFormat.BOTH, "CH1"),
    (LoggerMode.WAVEFORM, LoggerOutputFormat.CSV, "MATH"),
    (LoggerMode.MEASUREMENTS, LoggerOutputFormat.CSV, "CH1"),
    (LoggerMode.MIXED, LoggerOutputFormat.BOTH, "CH1"),
)


@pytest.mark.hardware
@pytest.mark.gui_hil
@pytest.mark.probe_comp
@pytest.mark.parametrize(("mode", "output", "source"), LOGGER_CASES)
def test_probe_comp_logger_modes_outputs_pause_health_and_report(
    mode: LoggerMode,
    output: LoggerOutputFormat,
    source: str,
    gui_window: Any,
    probe_comp_scope: DPO4054,
    qt_app: Any,
    tmp_path: Path,
) -> None:
    _configure_logger_case(gui_window, mode, output, source)
    gui_window.start_logger()
    assert gui_window._logger_state is LoggerState.RUNNING
    gui_window._logger_timer.stop()
    gui_window.pause_resume_logger()
    assert gui_window._logger_state is LoggerState.PAUSED
    gui_window.pause_resume_logger()
    assert gui_window._logger_state is LoggerState.RUNNING
    gui_window._logger_timer.stop()
    for _ in range(2):
        gui_window._logger_tick()
        _pump(qt_app, 0.03)
    writer = gui_window._logger_writer
    assert writer is not None
    _wait_until(qt_app, lambda: writer.snapshot().written_records >= 2, 15.0, "two Logger records")
    snapshot = writer.snapshot()
    assert snapshot.dropped_records == 0
    assert snapshot.error == ""
    assert int(gui_window.logger_health_captured_label.text()) >= 2
    gui_window.stop_logger()
    _wait_until(qt_app, lambda: not gui_window._logger_writer_active(), 15.0, "Logger writer shutdown")
    gui_window._logger_writer_monitor_tick()
    _pump(qt_app)
    suffixes = {path.suffix.lower() for path in (tmp_path / "logger").glob("logger_*")}
    if output is LoggerOutputFormat.CSV:
        assert ".csv" in suffixes
    elif output is LoggerOutputFormat.BINARY:
        assert ".dpo4log" in suffixes
    else:
        assert {".csv", ".dpo4log"}.issubset(suffixes)
    report = gui_window._logger_report_path
    assert report is not None and report.exists()
    assert report.suffix.lower() == ".json"


@pytest.mark.hardware
@pytest.mark.gui_hil
@pytest.mark.probe_comp
def test_probe_comp_logger_rotation_retention_and_bounded_queue(
    gui_window: Any, probe_comp_scope: DPO4054, qt_app: Any
) -> None:
    _configure_logger_case(gui_window, LoggerMode.WAVEFORM, LoggerOutputFormat.BOTH, "CH1")
    gui_window.logger_rotate_count_enabled.setChecked(True)
    gui_window.logger_rotate_count.setValue(1)
    gui_window.logger_keep_segments_enabled.setChecked(True)
    gui_window.logger_keep_segments.setValue(2)
    gui_window.logger_queue_records.setValue(2)
    gui_window.start_logger()
    assert gui_window._logger_state is LoggerState.RUNNING
    gui_window._logger_timer.stop()
    writer = gui_window._logger_writer
    assert writer is not None
    for expected in range(1, 4):
        gui_window._logger_tick()
        _wait_until(
            qt_app,
            lambda expected=expected: writer.snapshot().written_records >= expected,
            15.0,
            f"Logger record {expected}",
        )
    snapshot = writer.snapshot()
    assert snapshot.rotation_count >= 1
    assert snapshot.peak_records <= 2
    assert snapshot.dropped_records == 0
    gui_window.stop_logger()
    _wait_until(qt_app, lambda: not gui_window._logger_writer_active(), 15.0, "Logger writer shutdown")
    gui_window._logger_writer_monitor_tick()
    assert gui_window._logger_report_path is not None
    assert gui_window._logger_report_path.exists()


@pytest.mark.hardware
@pytest.mark.gui_hil
@pytest.mark.probe_comp
def test_logger_bus_gui_option_is_capability_gated(
    gui_window: Any, probe_comp_scope: DPO4054
) -> None:
    _configure_logger_common(gui_window)
    gui_window.logger_mode_combo.setCurrentText(LoggerMode.BUS.value)
    _select_only(gui_window.logger_bus_checks, {1})
    supported = bool(probe_comp_scope.supports_decoded_bus_events())
    if supported:
        pytest.skip(
            "Decoded BUS extraction is hardware-qualified on this scope; "
            "a serial-bus stimulus fixture is required for transaction-level BUS HIL."
        )
    gui_window.start_logger()
    assert not gui_window._logger_active()
    assert any(
        error and ("decoded" in text.lower() or "hardware-qualified" in text.lower())
        for _title, text, error in gui_window._hil_messages
    )


class Pico2206BAwg:
    """Small test-only wrapper around PicoSDK ps2000a built-in signal generator."""

    WAVE_TYPES = {"sine": 0, "square": 1, "triangle": 2}

    def __init__(self, ps: Any, assert_pico_ok: Any, handle: ctypes.c_int16, variant: str) -> None:
        self.ps = ps
        self.assert_pico_ok = assert_pico_ok
        self.handle = handle
        self.variant = variant

    def set_builtin(
        self,
        waveform: str,
        *,
        frequency_hz: float,
        pk_to_pk_v: float,
        offset_v: float = 0.0,
    ) -> None:
        status = self.ps.ps2000aSetSigGenBuiltIn(
            self.handle,
            int(round(offset_v * 1_000_000.0)),
            int(round(pk_to_pk_v * 1_000_000.0)),
            ctypes.c_int16(self.WAVE_TYPES[waveform]),
            float(frequency_hz),
            float(frequency_hz),
            0.0,
            1.0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        )
        self.assert_pico_ok(status)
        time.sleep(0.15)

    def close(self) -> None:
        try:
            self.set_builtin("sine", frequency_hz=1000.0, pk_to_pk_v=0.0)
        except Exception:
            pass
        self.assert_pico_ok(self.ps.ps2000aCloseUnit(self.handle))


@pytest.fixture(scope="session")
def pico2206b(gui_hil_resource: str) -> Iterator[Pico2206BAwg]:
    _require_env(
        "DPO4000_PICO2206B_HIL",
        "when PicoScope 2206B AWG output is physically connected to Tektronix CH1",
    )
    try:
        from picosdk.functions import assert_pico_ok
        from picosdk.ps2000a import ps2000a as ps
    except (ImportError, OSError) as exc:
        pytest.skip(f"PicoSDK ps2000a runtime is required for Pico 2206B HIL: {exc}")
    handle = ctypes.c_int16()
    serial = os.getenv("PICO2206B_SERIAL", "").strip()
    status = ps.ps2000aOpenUnit(ctypes.byref(handle), serial.encode() if serial else None)
    if status in {282, 286}:
        assert_pico_ok(ps.ps2000aChangePowerSource(handle, status))
    else:
        assert_pico_ok(status)
    buffer = ctypes.create_string_buffer(64)
    required = ctypes.c_int16()
    try:
        info_status = ps.ps2000aGetUnitInfo(handle, buffer, len(buffer), ctypes.byref(required), 3)
        assert_pico_ok(info_status)
        variant = buffer.value.decode(errors="replace")
    except Exception:
        variant = "unknown"
    expected = os.getenv("PICO2206B_EXPECT_VARIANT", "2206B").strip()
    if expected and expected.lower() not in variant.lower():
        ps.ps2000aCloseUnit(handle)
        pytest.fail(f"Expected Pico variant containing {expected!r}, got {variant!r}.")
    awg = Pico2206BAwg(ps, assert_pico_ok, handle, variant)
    try:
        yield awg
    finally:
        awg.close()


PICO_SIGNALS = (
    ("sine", 1_000.0, 1.0),
    ("square", 5_000.0, 1.5),
    ("triangle", 10_000.0, 1.0),
)


@pytest.mark.hardware
@pytest.mark.gui_hil
@pytest.mark.pico2206b
@pytest.mark.parametrize(("waveform", "frequency_hz", "pk_to_pk_v"), PICO_SIGNALS)
def test_pico2206b_awg_signals_are_measured_by_scope(
    waveform: str,
    frequency_hz: float,
    pk_to_pk_v: float,
    scope: DPO4054,
    pico2206b: Pico2206BAwg,
) -> None:
    pico2206b.set_builtin(waveform, frequency_hz=frequency_hz, pk_to_pk_v=pk_to_pk_v)
    _configure_scope_for_signal(
        scope, scale_v_per_div=max(0.1, pk_to_pk_v / 4.0), trigger_level_v=0.0
    )
    _assert_fresh_trigger(scope)
    measured_pk2pk = parse_measurement_value(scope.read_measurement_value(1))
    measured_frequency = parse_measurement_value(scope.read_measurement_value(2))
    assert measured_pk2pk == pytest.approx(pk_to_pk_v, rel=0.35, abs=0.10)
    assert measured_frequency == pytest.approx(frequency_hz, rel=0.10)


@pytest.mark.hardware
@pytest.mark.gui_hil
@pytest.mark.pico2206b
def test_pico2206b_drives_conditional_automation_and_mixed_logger(
    gui_window: Any,
    scope: DPO4054,
    pico2206b: Pico2206BAwg,
    qt_app: Any,
    tmp_path: Path,
) -> None:
    pico2206b.set_builtin("square", frequency_hz=2_000.0, pk_to_pk_v=1.2)
    _configure_scope_for_signal(scope, scale_v_per_div=0.3, trigger_level_v=0.0)
    _assert_fresh_trigger(scope)
    pk2pk = parse_measurement_value(scope.read_measurement_value(1))
    _configure_one_shot_automation(gui_window, "Conditional Capture", pk2pk)
    before = {path.resolve() for path in tmp_path.rglob("*") if path.is_file()}
    gui_window.run_automation_once()
    _wait_until(
        qt_app,
        lambda: {
            path.suffix.lower()
            for path in tmp_path.rglob("*")
            if path.is_file() and path.resolve() not in before
        }
        >= {".png", ".csv"},
        20.0,
        "Pico-driven conditional Automation artifacts",
    )
    _configure_logger_case(gui_window, LoggerMode.MIXED, LoggerOutputFormat.BOTH, "CH1")
    gui_window.start_logger()
    assert gui_window._logger_state is LoggerState.RUNNING
    gui_window._logger_timer.stop()
    writer = gui_window._logger_writer
    assert writer is not None
    gui_window._logger_tick()
    _wait_until(
        qt_app,
        lambda: writer.snapshot().written_records >= 1,
        15.0,
        "Pico-driven mixed Logger record",
    )
    gui_window.stop_logger()
    _wait_until(qt_app, lambda: not gui_window._logger_writer_active(), 15.0, "Logger writer shutdown")
    gui_window._logger_writer_monitor_tick()
    suffixes = {path.suffix.lower() for path in (tmp_path / "logger").glob("logger_*")}
    assert {".csv", ".dpo4log"}.issubset(suffixes)
    assert gui_window._logger_report_path is not None
    assert gui_window._logger_report_path.exists()
