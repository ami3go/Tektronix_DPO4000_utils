"""A7 Burst Capture automation UI."""

from __future__ import annotations

from pathlib import Path
from threading import Event

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..automation import (
    ArtifactAction,
    AutomationState,
    BurstConfig,
    BurstEventResult,
    PeriodicImageConfig,
    run_burst_event,
)
from .automation_conditional_review_window import QtScopeWindow as AutomationA6ReviewedQtScopeWindow
from .automation_window import FILE_PAGE_INDEX

BURST_CAPTURE_MODE = "Burst Capture"


class QtScopeWindow(AutomationA6ReviewedQtScopeWindow):
    """Reviewed A6 window extended with finite A7 burst capture."""

    def __init__(self, *args, **kwargs) -> None:
        self._burst_config_active: BurstConfig | None = None
        self._burst_cancel_event: Event | None = None
        self._burst_last_state = "--"
        super().__init__(*args, **kwargs)

    # ------------------------------------------------------------------
    # Burst configuration UI
    # ------------------------------------------------------------------
    def _build_automation_mode_card(self):
        card = super()._build_automation_mode_card()
        if self.automation_mode_combo.findText(BURST_CAPTURE_MODE) < 0:
            self.automation_mode_combo.addItem(BURST_CAPTURE_MODE)

        form = card.layout()
        self.automation_burst_row = QWidget()
        burst_form = QFormLayout(self.automation_burst_row)
        burst_form.setContentsMargins(0, 0, 0, 0)
        burst_form.setSpacing(8)

        self.automation_burst_count = QSpinBox()
        self.automation_burst_count.setRange(1, 1_000_000)
        self.automation_burst_count.setValue(10)
        self.automation_burst_count.valueChanged.connect(self._automation_update_recipe)

        self.automation_burst_delay = QDoubleSpinBox()
        self.automation_burst_delay.setRange(0.0, 604800.0)
        self.automation_burst_delay.setDecimals(3)
        self.automation_burst_delay.setSingleStep(0.1)
        self.automation_burst_delay.setValue(1.0)
        self.automation_burst_delay.setSuffix(" s")
        self.automation_burst_delay.valueChanged.connect(self._automation_update_recipe)

        self.automation_burst_action = QComboBox()
        self.automation_burst_action.addItems([action.value for action in ArtifactAction])
        self.automation_burst_action.currentTextChanged.connect(self._burst_action_changed)

        self.automation_burst_single = QCheckBox("Single acquisition before each event")
        self.automation_burst_single.setChecked(False)
        self.automation_burst_single.toggled.connect(self._burst_single_changed)

        self.automation_burst_poll = QDoubleSpinBox()
        self.automation_burst_poll.setRange(0.1, 10.0)
        self.automation_burst_poll.setDecimals(1)
        self.automation_burst_poll.setSingleStep(0.1)
        self.automation_burst_poll.setValue(0.5)
        self.automation_burst_poll.setSuffix(" s")
        self.automation_burst_poll.setEnabled(False)
        self.automation_burst_poll.valueChanged.connect(self._automation_update_recipe)

        burst_form.addRow("Successful events", self.automation_burst_count)
        burst_form.addRow("Delay after event", self.automation_burst_delay)
        burst_form.addRow("Artifacts", self.automation_burst_action)
        burst_form.addRow(self.automation_burst_single)
        burst_form.addRow("Single poll", self.automation_burst_poll)
        self.automation_burst_row.setVisible(False)
        if isinstance(form, QFormLayout):
            form.addRow("Burst", self.automation_burst_row)
        return card

    def _build_automation_output_card(self):
        card = self._card("Output & Retention")
        layout = QVBoxLayout(card)
        label = QLabel(
            "Burst Capture uses File-page PNG/CSV naming and the shared automation event "
            "sequence. Image + CSV uses paired collision-safe names. Single mode saves the "
            "artifacts before the next acquisition is armed."
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        hint = QLabel("Retention is added in A9.")
        hint.setObjectName("MutedLabel")
        layout.addWidget(hint)
        return self._prepare_drawer_card(card)

    def _build_automation_current_run_card(self):
        card = super()._build_automation_current_run_card()
        form = card.layout()
        if isinstance(form, QFormLayout):
            self.automation_burst_progress_label = QLabel("--")
            self.automation_burst_state_label = QLabel("--")
            form.addRow("Burst progress", self.automation_burst_progress_label)
            form.addRow("Burst state", self.automation_burst_state_label)
        return card

    def _burst_action_changed(self, *_args) -> None:
        self._sync_automation_actions_card()
        self._automation_update_recipe()

    def _burst_single_changed(self, *_args) -> None:
        self._automation_refresh_status()
        self._automation_update_recipe()

    def _burst_config(self, *, count_override: int | None = None) -> BurstConfig:
        count = int(count_override) if count_override is not None else int(self.automation_burst_count.value())
        return BurstConfig(
            count=count,
            delay_s=float(self.automation_burst_delay.value()),
            action=ArtifactAction(self.automation_burst_action.currentText()),
            single_acquisition=self.automation_burst_single.isChecked(),
            poll_interval_s=float(self.automation_burst_poll.value()),
        )

    def _automation_mode_changed(self, *_args) -> None:
        super()._automation_mode_changed(*_args)
        burst_mode = self._automation_mode() == BURST_CAPTURE_MODE
        row = getattr(self, "automation_burst_row", None)
        if row is not None:
            row.setVisible(burst_mode)
        periodic_row = getattr(self, "automation_periodic_row", None)
        if periodic_row is not None and burst_mode:
            periodic_row.setVisible(False)
        trigger_row = getattr(self, "automation_trigger_row", None)
        if trigger_row is not None and burst_mode:
            trigger_row.setVisible(False)
        self._sync_automation_actions_card()
        self._automation_update_recipe()
        self._automation_refresh_status()

    def _sync_automation_actions_card(self) -> None:
        if self._automation_mode() != BURST_CAPTURE_MODE:
            super()._sync_automation_actions_card()
            return
        combo = getattr(self, "automation_burst_action", None)
        action = ArtifactAction(combo.currentText()) if combo is not None else ArtifactAction.IMAGE
        image_box = getattr(self, "automation_save_image", None)
        csv_box = getattr(self, "automation_save_csv", None)
        hint = getattr(self, "automation_actions_hint", None)
        if image_box is not None:
            image_box.setChecked(action in {ArtifactAction.IMAGE, ArtifactAction.IMAGE_CSV})
        if csv_box is not None:
            csv_box.setChecked(action in {ArtifactAction.CSV, ArtifactAction.IMAGE_CSV})
        if hint is not None:
            hint.setText(
                "A7 captures a finite number of successful events. The next event is scheduled "
                "only after the previous event has completed."
            )

    def _automation_update_recipe(self, *_args) -> None:
        if self._automation_mode() != BURST_CAPTURE_MODE:
            super()._automation_update_recipe(*_args)
            return
        label = getattr(self, "automation_recipe_label", None)
        if label is None:
            return
        try:
            config = self._burst_config()
        except Exception as exc:  # noqa: BLE001 - inline validation feedback.
            label.setText(f"Invalid configuration: {exc}")
            return
        acquisition = (
            "Arm Single and wait for completion before each event; "
            if config.single_acquisition
            else "Use the current acquisition record; "
        )
        label.setText(
            f"{acquisition}save {config.action.value} until {config.count} successful event(s) "
            f"are complete, waiting {config.delay_s:g} s after each completed event."
        )

    def _automation_refresh_status(self) -> None:
        super()._automation_refresh_status()
        burst_selected = self._automation_mode() == BURST_CAPTURE_MODE
        if burst_selected:
            mode_label = getattr(self, "automation_mode_label", None)
            if mode_label is not None:
                mode_label.setText(BURST_CAPTURE_MODE)
        config = self._burst_config_active
        progress = getattr(self, "automation_burst_progress_label", None)
        state = getattr(self, "automation_burst_state_label", None)
        if progress is not None:
            progress.setText(
                f"{self._automation_controller.statistics.succeeded} / {config.count}"
                if config is not None
                else "--"
            )
        if state is not None:
            state.setText(self._burst_last_state)

        periodic_active = self._automation_controller.state in {
            AutomationState.RUNNING,
            AutomationState.PAUSED,
        }
        trigger_active = self._trigger_controller.state in {
            AutomationState.RUNNING,
            AutomationState.PAUSED,
        }
        operation_active = bool(getattr(self, "_operation_active", False))
        editable = not periodic_active and not trigger_active and not operation_active
        for name in (
            "automation_burst_count",
            "automation_burst_delay",
            "automation_burst_action",
            "automation_burst_single",
        ):
            control = getattr(self, name, None)
            if control is not None:
                control.setEnabled(editable)
        poll = getattr(self, "automation_burst_poll", None)
        if poll is not None:
            single = bool(getattr(self, "automation_burst_single", None) and self.automation_burst_single.isChecked())
            poll.setEnabled(editable and single)

    # ------------------------------------------------------------------
    # Burst dispatch and scheduling
    # ------------------------------------------------------------------
    def start_automation(self) -> None:
        if self._automation_mode() != BURST_CAPTURE_MODE:
            super().start_automation()
            return
        self._start_burst()

    def run_automation_once(self) -> None:
        if self._automation_mode() != BURST_CAPTURE_MODE:
            super().run_automation_once()
            return
        self._start_burst(count_override=1)

    def _automation_tick(self) -> None:
        if self._automation_mode() == BURST_CAPTURE_MODE:
            self._automation_burst_event()
            return
        super()._automation_tick()

    def _start_burst(self, *, count_override: int | None = None) -> None:
        if not bool(getattr(self, "_connection_ok", False)):
            self._message("Automation", "Test the scope connection before starting automation.", error=True)
            return
        if self._automation_controller.state is not AutomationState.IDLE:
            self._message("Automation", "Another periodic automation mode is already active.", error=True)
            return
        if self._trigger_controller.state is not AutomationState.IDLE:
            self._message("Automation", "Trigger automation is already active.", error=True)
            return
        try:
            config = self._burst_config(count_override=count_override)
            self._ensure_control_page_built(FILE_PAGE_INDEX)
            # The common controller owns state/no-overlap only; BurstConfig owns delay scheduling.
            self._automation_controller.start(PeriodicImageConfig(max(1.0, config.delay_s)))
        except Exception as exc:  # noqa: BLE001 - exact validation feedback.
            self._message("Automation", str(exc), error=True)
            return

        timer = self._automation_timer
        if timer is None:
            self._automation_controller.stop()
            self._message("Automation", "Automation timer is unavailable.", error=True)
            return
        timer.stop()
        self._burst_config_active = config
        self._burst_cancel_event = None
        self._burst_last_state = "Starting"
        self._automation_last_path = None
        self._automation_last_csv_path = None
        self._append_log(
            f"Automation A7 started: {config.count} successful {config.action.value} event(s), "
            f"delay {config.delay_s:g} s, Single={config.single_acquisition}"
        )
        self.statusBar().showMessage("Automation running: burst capture")
        self._automation_refresh_status()
        QTimer.singleShot(0, self._automation_burst_event)

    def _schedule_next_burst(self) -> None:
        config = self._burst_config_active
        timer = self._automation_timer
        if (
            config is None
            or timer is None
            or self._automation_controller.state is not AutomationState.RUNNING
        ):
            return
        timer.stop()
        timer.setInterval(max(1, int(round(config.delay_s * 1000.0))))
        timer.start()
        self._burst_last_state = f"Waiting {config.delay_s:g} s"
        self._automation_refresh_status()

    def _build_burst_paths(self, sequence: int, action: ArtifactAction):
        return self._build_conditional_paths(sequence, action)

    def _automation_burst_event(self) -> None:
        timer = self._automation_timer
        if timer is not None:
            timer.stop()
        controller = self._automation_controller
        config = self._burst_config_active
        if controller.state is not AutomationState.RUNNING or config is None:
            return
        if controller.statistics.succeeded >= config.count:
            self._finish_burst_complete()
            return

        token = controller.begin_event()
        if token is None:
            self._automation_refresh_status()
            return
        try:
            image_path, csv_path = self._build_burst_paths(token.sequence, config.action)
            for path in (image_path, csv_path):
                if path is not None:
                    path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001 - output validation failure.
            controller.finish_event(token, success=False, error=str(exc))
            self._stop_burst_after_failure(f"Burst output error: {exc}")
            return

        cancel = Event()
        self._burst_cancel_event = cancel
        self._burst_last_state = (
            "Waiting for Single" if config.single_acquisition else "Saving artifacts"
        )
        self._automation_refresh_status()
        result = self._run_action(
            f"Burst capture #{token.sequence:04d}",
            lambda scope: run_burst_event(
                scope,
                cancel,
                config,
                image_path=str(image_path) if image_path is not None else None,
                csv_path=str(csv_path) if csv_path is not None else None,
            ),
        )
        self._burst_cancel_event = None

        if token.generation != controller.generation:
            return
        if not isinstance(result, BurstEventResult):
            controller.finish_event(
                token,
                success=False,
                error=str(getattr(self, "_last_action", "Burst event failed")),
            )
            self._stop_burst_after_failure("Burst event failed")
            return
        if result.cancelled:
            controller.finish_skipped(token, reason="Burst event cancelled")
            self._burst_last_state = (
                "Paused" if controller.state is AutomationState.PAUSED else "Cancelled"
            )
            self._automation_refresh_status()
            return

        artifacts = result.artifacts
        if artifacts is None or not artifacts.success:
            error = artifacts.error if artifacts is not None else "Burst artifacts were not saved"
            controller.finish_event(token, success=False, error=error)
            self._stop_burst_after_failure(error)
            return

        accepted = controller.finish_event(token, success=True)
        if not accepted:
            return
        if artifacts.image_path is not None:
            self._automation_last_path = Path(artifacts.image_path)
            self._last_image_path = Path(artifacts.image_path)
        if artifacts.csv_path is not None:
            self._automation_last_csv_path = Path(artifacts.csv_path)
            if artifacts.image_path is None:
                self._automation_last_path = Path(artifacts.csv_path)
        successes = controller.statistics.succeeded
        self._burst_last_state = "Captured"
        self._append_log(
            f"A7 burst event {successes}/{config.count}: {config.action.value}"
        )
        self.statusBar().showMessage(f"Burst capture {successes}/{config.count} complete")

        if successes >= config.count:
            self._finish_burst_complete()
            return
        if controller.state is AutomationState.RUNNING:
            self._schedule_next_burst()
        else:
            self._automation_refresh_status()

    def _finish_burst_complete(self) -> None:
        timer = self._automation_timer
        if timer is not None:
            timer.stop()
        config = self._burst_config_active
        successes = self._automation_controller.statistics.succeeded
        self._burst_last_state = "Complete"
        self._automation_controller.stop()
        self._append_log(f"Automation A7 complete: {successes} successful event(s)")
        if config is not None:
            self.statusBar().showMessage(f"Burst complete: {successes}/{config.count}")
        self._automation_refresh_status()

    def _stop_burst_after_failure(self, error: str) -> None:
        timer = self._automation_timer
        if timer is not None:
            timer.stop()
        self._burst_last_state = f"Failed: {error}"
        self._automation_controller.stop()
        self._append_log(f"Automation A7 failed: {error}")
        self.statusBar().showMessage("Burst capture failed")
        self._automation_refresh_status()

    def pause_resume_automation(self) -> None:
        if self._automation_mode() != BURST_CAPTURE_MODE:
            super().pause_resume_automation()
            return
        controller = self._automation_controller
        timer = self._automation_timer
        if controller.state is AutomationState.RUNNING:
            controller.pause()
            if timer is not None:
                timer.stop()
            cancel = self._burst_cancel_event
            if cancel is not None:
                cancel.set()
            self._burst_last_state = "Paused"
            self._append_log("Burst automation paused")
            self._automation_refresh_status()
            return
        if controller.state is AutomationState.PAUSED:
            controller.resume()
            self._append_log("Burst automation resumed")
            self._schedule_next_burst()
            return
        super().pause_resume_automation()

    def stop_automation(self) -> None:
        if self._automation_mode() != BURST_CAPTURE_MODE:
            super().stop_automation()
            return
        controller = self._automation_controller
        if controller.state not in {AutomationState.RUNNING, AutomationState.PAUSED}:
            return
        cancel = self._burst_cancel_event
        if cancel is not None:
            cancel.set()
        timer = self._automation_timer
        if timer is not None:
            timer.stop()
        controller.stop()
        self._burst_last_state = "Stopped"
        self._append_log("Burst automation stopped")
        self.statusBar().showMessage("Burst automation stopped")
        self._automation_refresh_status()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name.
        cancel = self._burst_cancel_event
        if cancel is not None:
            cancel.set()
        super().closeEvent(event)


__all__ = ["BURST_CAPTURE_MODE", "QtScopeWindow"]
