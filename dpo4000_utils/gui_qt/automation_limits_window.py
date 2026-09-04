"""A8 run count/duration limits for the Automation tab."""

from __future__ import annotations

import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QSpinBox,
)

from ..automation import AutomationState, RunLimits, RunLimitTracker
from .automation_burst_window import QtScopeWindow as AutomationA7QtScopeWindow

RUN_LIMIT_WATCHDOG_MS = 250
_DURATION_FACTORS = {"seconds": 1.0, "minutes": 60.0, "hours": 3600.0}


class QtScopeWindow(AutomationA7QtScopeWindow):
    """A7 window extended with shared A8 run limits."""

    def __init__(self, *args, **kwargs) -> None:
        self._run_limit_tracker = RunLimitTracker(RunLimits())
        self._run_limit_controller_kind = "automation"
        self._run_limit_stop_reason = ""
        self._run_limit_watchdog: QTimer | None = None
        super().__init__(*args, **kwargs)
        self._run_limit_watchdog = QTimer(self)
        self._run_limit_watchdog.setInterval(RUN_LIMIT_WATCHDOG_MS)
        self._run_limit_watchdog.setSingleShot(False)
        self._run_limit_watchdog.timeout.connect(self._run_limit_watchdog_tick)

    def _build_automation_run_limits_card(self):
        card = self._card("Run Limits")
        form = QFormLayout(card)
        self._prepare_form(form)

        self.automation_limit_count_enabled = QCheckBox("Stop after successful events")
        self.automation_limit_count_enabled.setChecked(False)
        self.automation_limit_count = QSpinBox()
        self.automation_limit_count.setRange(1, 1_000_000_000)
        self.automation_limit_count.setValue(100)

        self.automation_limit_duration_enabled = QCheckBox("Stop after elapsed duration")
        self.automation_limit_duration_enabled.setChecked(False)
        self.automation_limit_duration = QDoubleSpinBox()
        self.automation_limit_duration.setRange(0.1, 8760.0)
        self.automation_limit_duration.setDecimals(2)
        self.automation_limit_duration.setValue(2.0)
        self.automation_limit_duration_unit = QComboBox()
        self.automation_limit_duration_unit.addItems(["seconds", "minutes", "hours"])
        self.automation_limit_duration_unit.setCurrentText("hours")

        self.automation_limit_remaining_count = QLabel("Unlimited")
        self.automation_limit_remaining_time = QLabel("Unlimited")
        self.automation_limit_reason = QLabel("--")
        self.automation_limit_reason.setWordWrap(True)

        form.addRow(self.automation_limit_count_enabled, self.automation_limit_count)
        form.addRow(self.automation_limit_duration_enabled, self.automation_limit_duration)
        form.addRow("Duration unit", self.automation_limit_duration_unit)
        form.addRow("Remaining events", self.automation_limit_remaining_count)
        form.addRow("Remaining time", self.automation_limit_remaining_time)
        form.addRow("Stop reason", self.automation_limit_reason)

        for control in (
            self.automation_limit_count_enabled,
            self.automation_limit_count,
            self.automation_limit_duration_enabled,
            self.automation_limit_duration,
            self.automation_limit_duration_unit,
        ):
            if hasattr(control, "toggled"):
                control.toggled.connect(self._automation_update_recipe)
            if hasattr(control, "valueChanged"):
                control.valueChanged.connect(self._automation_update_recipe)
            if hasattr(control, "currentTextChanged"):
                control.currentTextChanged.connect(self._automation_update_recipe)
        return self._prepare_drawer_card(card)

    def _selected_run_limits(self) -> RunLimits:
        max_events = (
            int(self.automation_limit_count.value())
            if self.automation_limit_count_enabled.isChecked()
            else None
        )
        max_duration_s = None
        if self.automation_limit_duration_enabled.isChecked():
            factor = _DURATION_FACTORS[self.automation_limit_duration_unit.currentText()]
            max_duration_s = float(self.automation_limit_duration.value()) * factor
        return RunLimits(max_events=max_events, max_duration_s=max_duration_s)

    def _automation_update_recipe(self, *_args) -> None:
        super()._automation_update_recipe(*_args)
        label = getattr(self, "automation_recipe_label", None)
        if label is None or not hasattr(self, "automation_limit_count_enabled"):
            return
        try:
            limits = self._selected_run_limits()
        except Exception:
            return
        parts: list[str] = []
        if limits.max_events is not None:
            parts.append(f"stop after {limits.max_events} successful event(s)")
        if limits.max_duration_s is not None:
            parts.append(f"stop after {limits.max_duration_s:g} s elapsed")
        if parts:
            label.setText(f"{label.text()} Run limit: {' or '.join(parts)} (first reached).")

    def _automation_any_active(self) -> bool:
        return self._automation_controller.state in {
            AutomationState.RUNNING,
            AutomationState.PAUSED,
        } or self._trigger_controller.state in {
            AutomationState.RUNNING,
            AutomationState.PAUSED,
        }

    def _run_limit_success_count(self) -> int:
        if self._run_limit_controller_kind == "trigger":
            return int(self._trigger_controller.statistics.succeeded)
        return int(self._automation_controller.statistics.succeeded)

    def _run_limit_status(self):
        return self._run_limit_tracker.status(
            self._run_limit_success_count(),
            time.monotonic(),
        )

    def _start_run_limit_tracking_if_active(self, limits: RunLimits) -> None:
        if not self._automation_any_active():
            return
        self._run_limit_controller_kind = (
            "trigger"
            if self._trigger_controller.state in {AutomationState.RUNNING, AutomationState.PAUSED}
            else "automation"
        )
        self._run_limit_tracker = RunLimitTracker(limits)
        self._run_limit_tracker.start(time.monotonic())
        self._run_limit_stop_reason = ""
        watchdog = self._run_limit_watchdog
        if watchdog is not None:
            watchdog.start()
        self._automation_refresh_status()

    def start_automation(self) -> None:
        try:
            limits = self._selected_run_limits()
        except Exception as exc:  # noqa: BLE001 - exact UI validation feedback.
            self._message("Automation", str(exc), error=True)
            return
        super().start_automation()
        self._start_run_limit_tracking_if_active(limits)

    def _stop_for_run_limit(self, reason: str) -> None:
        if not self._automation_any_active():
            return
        self._run_limit_stop_reason = str(reason)
        watchdog = self._run_limit_watchdog
        if watchdog is not None:
            watchdog.stop()
        self._append_log(f"Automation A8 limit stop: {reason}")
        super().stop_automation()
        self.statusBar().showMessage(f"Automation stopped: {reason}")
        self._automation_refresh_status()

    def _check_run_limits(self) -> bool:
        if not self._run_limit_tracker.started:
            return False
        status = self._run_limit_status()
        if status.reached and self._automation_any_active():
            self._stop_for_run_limit(status.reason)
            return True
        return bool(status.reached)

    def _run_limit_watchdog_tick(self) -> None:
        self._check_run_limits()
        self._automation_refresh_status()

    def _automation_tick(self) -> None:
        if self._check_run_limits():
            return
        super()._automation_tick()
        self._check_run_limits()

    def _trigger_cycle(self) -> None:
        if self._check_run_limits():
            return
        super()._trigger_cycle()
        self._check_run_limits()

    def _trigger_bundle_cycle(self) -> None:
        if self._check_run_limits():
            return
        super()._trigger_bundle_cycle()
        self._check_run_limits()

    def _schedule_next_burst(self) -> None:
        if self._check_run_limits():
            return
        super()._schedule_next_burst()

    def stop_automation(self) -> None:
        was_active = self._automation_any_active()
        watchdog = self._run_limit_watchdog
        if watchdog is not None:
            watchdog.stop()
        if was_active and not self._run_limit_stop_reason:
            self._run_limit_stop_reason = "Stopped manually"
        super().stop_automation()
        self._automation_refresh_status()

    def _automation_refresh_status(self) -> None:
        super()._automation_refresh_status()
        if not hasattr(self, "automation_limit_reason"):
            return
        status = None
        if self._run_limit_tracker.started:
            try:
                status = self._run_limit_status()
            except Exception:
                status = None
        if status is None:
            self.automation_limit_remaining_count.setText("Unlimited")
            self.automation_limit_remaining_time.setText("Unlimited")
        else:
            self.automation_limit_remaining_count.setText(
                "Unlimited"
                if status.remaining_events is None
                else str(status.remaining_events)
            )
            self.automation_limit_remaining_time.setText(
                "Unlimited"
                if status.remaining_s is None
                else f"{status.remaining_s:.1f} s"
            )
        reason = self._run_limit_stop_reason or (
            status.reason if status is not None and status.reason else "--"
        )
        self.automation_limit_reason.setText(reason)

        editable = not self._automation_any_active() and not bool(
            getattr(self, "_operation_active", False)
        )
        for name in (
            "automation_limit_count_enabled",
            "automation_limit_count",
            "automation_limit_duration_enabled",
            "automation_limit_duration",
            "automation_limit_duration_unit",
        ):
            control = getattr(self, name, None)
            if control is not None:
                control.setEnabled(editable)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name.
        watchdog = self._run_limit_watchdog
        if watchdog is not None:
            watchdog.stop()
        super().closeEvent(event)


__all__ = ["RUN_LIMIT_WATCHDOG_MS", "QtScopeWindow"]
