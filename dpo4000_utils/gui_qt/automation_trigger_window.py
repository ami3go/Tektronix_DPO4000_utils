"""A2 Image-on-Trigger automation UI.

Trigger waiting is performed on the existing scope worker through public driver
methods.  No SCPI or PyVISA operation is implemented in this Qt layer.
"""

from __future__ import annotations

from pathlib import Path
from threading import Event

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QWidget,
)

from ..automation import (
    AutomationState,
    PeriodicImageConfig,
    TriggerImageConfig,
    TriggerImageController,
    TriggerWaitResult,
    trigger_acquisition_complete,
)
from .automation_review_window import QtScopeWindow as AutomationA1ReviewedQtScopeWindow

PERIODIC_IMAGE_MODE = "Periodic Image"
TRIGGER_IMAGE_MODE = "Image on Trigger"


class QtScopeWindow(AutomationA1ReviewedQtScopeWindow):
    """A1 reviewed window extended with A2 Image on Trigger."""

    def __init__(self, *args, **kwargs) -> None:
        self._trigger_controller = TriggerImageController()
        self._trigger_cancel_event: Event | None = None
        self._trigger_last_state = "--"
        super().__init__(*args, **kwargs)

    # ------------------------------------------------------------------
    # Dynamic mode UI
    # ------------------------------------------------------------------
    def _build_automation_mode_card(self):
        card = self._card("Automation Mode")
        form = QFormLayout(card)
        self._prepare_form(form)

        self.automation_mode_combo = QComboBox()
        self.automation_mode_combo.addItems([PERIODIC_IMAGE_MODE, TRIGGER_IMAGE_MODE])
        self.automation_mode_combo.currentTextChanged.connect(self._automation_mode_changed)

        self.automation_interval_value = QDoubleSpinBox()
        self.automation_interval_value.setRange(1.0, 604800.0)
        self.automation_interval_value.setDecimals(1)
        self.automation_interval_value.setValue(10.0)
        self.automation_interval_value.valueChanged.connect(self._automation_update_recipe)
        self.automation_interval_unit = QComboBox()
        self.automation_interval_unit.addItems(["seconds", "minutes", "hours"])
        self.automation_interval_unit.currentTextChanged.connect(self._automation_update_recipe)

        self.automation_periodic_row = QWidget()
        periodic_layout = QHBoxLayout(self.automation_periodic_row)
        periodic_layout.setContentsMargins(0, 0, 0, 0)
        periodic_layout.setSpacing(8)
        periodic_layout.addWidget(self.automation_interval_value, 1)
        periodic_layout.addWidget(self.automation_interval_unit, 1)

        self.automation_trigger_poll = QDoubleSpinBox()
        self.automation_trigger_poll.setRange(0.1, 10.0)
        self.automation_trigger_poll.setDecimals(1)
        self.automation_trigger_poll.setSingleStep(0.1)
        self.automation_trigger_poll.setValue(0.5)
        self.automation_trigger_poll.setSuffix(" s")
        self.automation_trigger_poll.valueChanged.connect(self._automation_update_recipe)
        self.automation_trigger_rearm = QCheckBox("Re-arm Single after each saved image")
        self.automation_trigger_rearm.setChecked(True)
        self.automation_trigger_rearm.toggled.connect(self._automation_update_recipe)

        self.automation_trigger_row = QWidget()
        trigger_layout = QFormLayout(self.automation_trigger_row)
        trigger_layout.setContentsMargins(0, 0, 0, 0)
        trigger_layout.setSpacing(8)
        trigger_layout.addRow("Poll", self.automation_trigger_poll)
        trigger_layout.addRow(self.automation_trigger_rearm)

        form.addRow("Mode", self.automation_mode_combo)
        form.addRow("Every", self.automation_periodic_row)
        form.addRow("Trigger", self.automation_trigger_row)
        self.automation_trigger_row.setVisible(False)
        return self._prepare_drawer_card(card)

    def _build_automation_current_run_card(self):
        card = super()._build_automation_current_run_card()
        form = card.layout()
        if isinstance(form, QFormLayout):
            self.automation_trigger_state_label = QLabel("--")
            form.addRow("Trigger state", self.automation_trigger_state_label)
        return card

    def _automation_mode(self) -> str:
        combo = getattr(self, "automation_mode_combo", None)
        return combo.currentText() if combo is not None else PERIODIC_IMAGE_MODE

    def _automation_mode_changed(self, *_args) -> None:
        trigger_mode = self._automation_mode() == TRIGGER_IMAGE_MODE
        periodic_row = getattr(self, "automation_periodic_row", None)
        trigger_row = getattr(self, "automation_trigger_row", None)
        if periodic_row is not None:
            periodic_row.setVisible(not trigger_mode)
        if trigger_row is not None:
            trigger_row.setVisible(trigger_mode)
        mode_label = getattr(self, "automation_mode_label", None)
        if mode_label is not None:
            mode_label.setText(self._automation_mode())
        self._automation_update_recipe()
        self._automation_refresh_status()

    def _automation_update_recipe(self, *_args) -> None:
        label = getattr(self, "automation_recipe_label", None)
        if label is None:
            return
        if self._automation_mode() == PERIODIC_IMAGE_MODE:
            try:
                config = PeriodicImageConfig(self._automation_interval_seconds())
            except Exception as exc:  # noqa: BLE001 - inline configuration diagnostic.
                label.setText(f"Invalid configuration: {exc}")
                return
            label.setText(
                f"Every {config.interval_s:g} seconds, save one "
                f"PNG image using the File-page naming settings."
            )
            return

        try:
            config = TriggerImageConfig(
                poll_interval_s=float(self.automation_trigger_poll.value()),
                rearm=self.automation_trigger_rearm.isChecked(),
            )
        except Exception as exc:  # noqa: BLE001 - inline configuration diagnostic.
            label.setText(f"Invalid configuration: {exc}")
            return
        rearm = "then re-arm Single" if config.rearm else "then stop"
        label.setText(
            "Arm a Single acquisition, wait for the acquisition to stop and the trigger to save, "
            f"save one PNG, {rearm}. Poll interval {config.poll_interval_s:g} s."
        )

    # ------------------------------------------------------------------
    # State/control presentation
    # ------------------------------------------------------------------
    def _automation_refresh_status(self) -> None:
        super()._automation_refresh_status()
        trigger = getattr(self, "_trigger_controller", None)
        if trigger is None:
            return
        trigger_selected = self._automation_mode() == TRIGGER_IMAGE_MODE
        trigger_active = trigger.state in {AutomationState.RUNNING, AutomationState.PAUSED}
        if not trigger_selected and not trigger_active:
            return

        state_label = getattr(self, "automation_state_label", None)
        if state_label is not None:
            state_label.setText(trigger.state.value)
        mode_label = getattr(self, "automation_mode_label", None)
        if mode_label is not None:
            mode_label.setText(TRIGGER_IMAGE_MODE)
        stats = trigger.statistics
        for name, value in (
            ("automation_capture_count_label", stats.succeeded),
            ("automation_skipped_count_label", stats.skipped),
            ("automation_failed_count_label", stats.failed),
        ):
            label = getattr(self, name, None)
            if label is not None:
                label.setText(str(value))
        trigger_state_label = getattr(self, "automation_trigger_state_label", None)
        if trigger_state_label is not None:
            trigger_state_label.setText(self._trigger_last_state)

        operation_active = bool(getattr(self, "_operation_active", False))
        connection_ok = bool(getattr(self, "_connection_ok", False))
        start = getattr(self, "automation_start_button", None)
        run_once = getattr(self, "automation_run_once_button", None)
        pause = getattr(self, "automation_pause_button", None)
        stop = getattr(self, "automation_stop_button", None)
        mode_combo = getattr(self, "automation_mode_combo", None)
        if start is not None:
            start.setEnabled(not trigger_active and not operation_active and connection_ok)
        if run_once is not None:
            run_once.setEnabled(not trigger_active and not operation_active and connection_ok)
        if pause is not None:
            pause.setEnabled(trigger_active)
            pause.setText("Resume" if trigger.state is AutomationState.PAUSED else "Pause")
        if stop is not None:
            stop.setEnabled(trigger_active)
        if mode_combo is not None:
            mode_combo.setEnabled(
                not trigger_active
                and self._automation_controller.state is not AutomationState.RUNNING
            )

    # ------------------------------------------------------------------
    # Mode dispatch
    # ------------------------------------------------------------------
    def start_automation(self) -> None:
        if self._automation_mode() == PERIODIC_IMAGE_MODE:
            super().start_automation()
            return
        self._start_trigger_automation(rearm=self.automation_trigger_rearm.isChecked())

    def run_automation_once(self) -> None:
        if self._automation_mode() == PERIODIC_IMAGE_MODE:
            super().run_automation_once()
            return
        self._start_trigger_automation(rearm=False)

    def pause_resume_automation(self) -> None:
        trigger = self._trigger_controller
        if trigger.state is AutomationState.RUNNING:
            trigger.pause()
            cancel = self._trigger_cancel_event
            if cancel is not None:
                cancel.set()
            self._append_log("Trigger automation paused; current Single acquisition cancelled")
            self._automation_refresh_status()
            return
        if trigger.state is AutomationState.PAUSED:
            trigger.resume()
            self._append_log("Trigger automation resumed")
            self._automation_refresh_status()
            QTimer.singleShot(0, self._trigger_cycle)
            return
        super().pause_resume_automation()

    def stop_automation(self) -> None:
        trigger = self._trigger_controller
        if trigger.state in {AutomationState.RUNNING, AutomationState.PAUSED}:
            cancel = self._trigger_cancel_event
            if cancel is not None:
                cancel.set()
            trigger.stop()
            self._append_log("Trigger automation stopped")
            self.statusBar().showMessage("Trigger automation stopped")
            self._automation_refresh_status()
            return
        super().stop_automation()

    # ------------------------------------------------------------------
    # Trigger acquisition worker cycle
    # ------------------------------------------------------------------
    def _start_trigger_automation(self, *, rearm: bool) -> None:
        if not bool(getattr(self, "_connection_ok", False)):
            self._message(
                "Automation", "Test the scope connection before starting automation.", error=True
            )
            return
        if self._automation_controller.state is not AutomationState.IDLE:
            self._message("Automation", "Periodic automation is already active.", error=True)
            return
        try:
            config = TriggerImageConfig(
                poll_interval_s=float(self.automation_trigger_poll.value()),
                rearm=bool(rearm),
            )
            self._ensure_control_page_built(6)
            self._trigger_controller.start(config)
        except Exception as exc:  # noqa: BLE001 - show exact validation failure.
            self._message("Automation", str(exc), error=True)
            return

        self._trigger_last_state = "ARMING"
        self._append_log(
            f"Automation A2 started: Single -> wait -> image; poll {config.poll_interval_s:g} s"
        )
        self._automation_refresh_status()
        QTimer.singleShot(0, self._trigger_cycle)

    def _trigger_cycle(self) -> None:
        trigger = self._trigger_controller
        if trigger.state is not AutomationState.RUNNING:
            return
        config = trigger.config
        if config is None:
            trigger.stop()
            self._automation_refresh_status()
            return
        token = trigger.begin_cycle()
        if token is None:
            self._automation_refresh_status()
            return

        cancel = Event()
        self._trigger_cancel_event = cancel
        self._trigger_last_state = "ARMED"
        self._automation_refresh_status()

        result = self._run_action(
            f"Waiting for triggered acquisition #{token.sequence:04d}",
            lambda scope: self._wait_for_triggered_single(
                scope,
                cancel,
                poll_interval_s=config.poll_interval_s,
            ),
        )
        self._trigger_cancel_event = None

        if token.generation != getattr(trigger, "_generation", token.generation):
            return
        if trigger.state is not AutomationState.RUNNING:
            trigger.cancel_cycle(token)
            self._automation_refresh_status()
            return
        if not isinstance(result, TriggerWaitResult):
            trigger.finish_cycle(
                token, success=False, error="Could not read acquisition completion state"
            )
            trigger.stop()
            self._automation_refresh_status()
            return

        self._trigger_last_state = result.trigger_state or self._trigger_last_state
        if result.cancelled:
            trigger.cancel_cycle(token)
            self._automation_refresh_status()
            return
        if not result.completed:
            trigger.finish_cycle(token, success=False, error="Single acquisition did not complete")
            trigger.stop()
            self._automation_refresh_status()
            return

        self._save_triggered_image(token)
        if trigger.state is not AutomationState.RUNNING:
            self._automation_refresh_status()
            return
        if config.rearm:
            QTimer.singleShot(0, self._trigger_cycle)
        else:
            trigger.stop()
            self._automation_refresh_status()

    @staticmethod
    def _wait_for_triggered_single(
        scope,
        cancel: Event,
        *,
        poll_interval_s: float,
    ) -> TriggerWaitResult:
        """Arm and wait on the scope-worker thread using public driver methods only."""
        scope.single_acquisition()
        last_active = True
        last_trigger_state = "ARMED"
        while True:
            if cancel.is_set():
                scope.stop_acquisition()
                return TriggerWaitResult(
                    completed=False,
                    cancelled=True,
                    acquisition_active=last_active,
                    trigger_state=last_trigger_state,
                )
            last_active = bool(scope.get_acquisition_state())
            last_trigger_state = str(scope.get_trigger_state())
            if trigger_acquisition_complete(
                acquisition_active=last_active,
                trigger_state=last_trigger_state,
            ):
                return TriggerWaitResult(
                    completed=True,
                    acquisition_active=last_active,
                    trigger_state=last_trigger_state,
                )
            if cancel.wait(poll_interval_s):
                scope.stop_acquisition()
                return TriggerWaitResult(
                    completed=False,
                    cancelled=True,
                    acquisition_active=last_active,
                    trigger_state=last_trigger_state,
                )

    def _save_triggered_image(self, token) -> None:
        trigger = self._trigger_controller
        try:
            path = self._automation_build_png_path(token.sequence)
            path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001 - file validation failure.
            trigger.finish_cycle(token, success=False, error=str(exc))
            trigger.stop()
            self._automation_refresh_status()
            return

        result = self._run_action(
            f"Saving triggered image #{token.sequence:04d}",
            lambda scope: str(scope.save_image_path(path)),
        )
        if isinstance(result, str) and result:
            saved_path = Path(result)
            if trigger.finish_cycle(token, success=True):
                self._automation_last_path = saved_path
                self._last_image_path = saved_path
                self.statusBar().showMessage(f"Triggered image saved: {saved_path.name}")
        else:
            trigger.finish_cycle(
                token,
                success=False,
                error=str(getattr(self, "_last_action", "Triggered image save failed")),
            )
            trigger.stop()
        self._automation_refresh_status()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name.
        cancel = self._trigger_cancel_event
        if cancel is not None:
            cancel.set()
        self._trigger_controller.stop()
        super().closeEvent(event)


__all__ = ["PERIODIC_IMAGE_MODE", "TRIGGER_IMAGE_MODE", "QtScopeWindow"]
