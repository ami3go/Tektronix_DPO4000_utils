"""A6 Conditional Capture automation UI."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
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
    ConditionalCaptureConfig,
    ConditionalEvaluator,
    ConditionalPollResult,
    PeriodicImageConfig,
    append_sequence,
    collision_safe_bundle_paths,
    collision_safe_path,
    run_conditional_poll,
)
from ..gui.config import FileNaming, build_output_path
from .automation_measurement_review_window import QtScopeWindow as AutomationA5ReviewedQtScopeWindow
from .automation_window import FILE_PAGE_INDEX

CONDITIONAL_CAPTURE_MODE = "Conditional Capture"
_CONDITION_OPERATOR_ITEMS = (
    (">", ">"),
    (">=", ">="),
    ("<", "<"),
    ("<=", "<="),
    ("inside [low, high]", "inside"),
    ("outside [low, high]", "outside"),
    ("absolute delta >", "abs_delta"),
)


class QtScopeWindow(AutomationA5ReviewedQtScopeWindow):
    """A5 reviewed window extended with measurement-driven conditional capture."""

    def __init__(self, *args, **kwargs) -> None:
        self._conditional_evaluator: ConditionalEvaluator | None = None
        self._conditional_action_active = ArtifactAction.IMAGE
        self._conditional_last_value: float | None = None
        self._conditional_last_state = "--"
        super().__init__(*args, **kwargs)

    def _build_automation_mode_card(self):
        card = super()._build_automation_mode_card()
        if self.automation_mode_combo.findText(CONDITIONAL_CAPTURE_MODE) < 0:
            self.automation_mode_combo.addItem(CONDITIONAL_CAPTURE_MODE)

        form = card.layout()
        self.automation_condition_row = QWidget()
        condition_form = QFormLayout(self.automation_condition_row)
        condition_form.setContentsMargins(0, 0, 0, 0)
        condition_form.setSpacing(8)

        self.automation_condition_slot = QComboBox()
        for slot in range(1, 9):
            self.automation_condition_slot.addItem(f"MEAS{slot}", slot)
        self.automation_condition_slot.currentIndexChanged.connect(self._automation_update_recipe)

        self.automation_condition_operator = QComboBox()
        for label, value in _CONDITION_OPERATOR_ITEMS:
            self.automation_condition_operator.addItem(label, value)
        self.automation_condition_operator.currentIndexChanged.connect(
            self._condition_operator_changed
        )

        self.automation_condition_threshold = QDoubleSpinBox()
        self.automation_condition_threshold.setRange(-1.0e15, 1.0e15)
        self.automation_condition_threshold.setDecimals(6)
        self.automation_condition_threshold.setValue(1.0)
        self.automation_condition_threshold.valueChanged.connect(self._automation_update_recipe)

        self.automation_condition_high = QDoubleSpinBox()
        self.automation_condition_high.setRange(-1.0e15, 1.0e15)
        self.automation_condition_high.setDecimals(6)
        self.automation_condition_high.setValue(2.0)
        self.automation_condition_high.setEnabled(False)
        self.automation_condition_high.valueChanged.connect(self._automation_update_recipe)

        self.automation_condition_debounce = QSpinBox()
        self.automation_condition_debounce.setRange(1, 1000)
        self.automation_condition_debounce.setValue(3)
        self.automation_condition_debounce.valueChanged.connect(self._automation_update_recipe)

        self.automation_condition_cooldown = QDoubleSpinBox()
        self.automation_condition_cooldown.setRange(1.0, 604800.0)
        self.automation_condition_cooldown.setDecimals(1)
        self.automation_condition_cooldown.setValue(30.0)
        self.automation_condition_cooldown.setSuffix(" s")
        self.automation_condition_cooldown.valueChanged.connect(self._automation_update_recipe)

        self.automation_condition_action = QComboBox()
        self.automation_condition_action.addItems([action.value for action in ArtifactAction])
        self.automation_condition_action.currentTextChanged.connect(self._condition_action_changed)

        condition_form.addRow("Measurement", self.automation_condition_slot)
        condition_form.addRow("Operator", self.automation_condition_operator)
        condition_form.addRow("Threshold / low", self.automation_condition_threshold)
        condition_form.addRow("High (range only)", self.automation_condition_high)
        condition_form.addRow("Consecutive matches", self.automation_condition_debounce)
        condition_form.addRow("Cooldown", self.automation_condition_cooldown)
        condition_form.addRow("Capture", self.automation_condition_action)
        self.automation_condition_row.setVisible(False)
        if isinstance(form, QFormLayout):
            form.addRow("Condition", self.automation_condition_row)
        return card

    def _build_automation_output_card(self):
        card = self._card("Output & Retention")
        layout = QVBoxLayout(card)
        label = QLabel(
            "Conditional Capture uses the File-page PNG/CSV naming settings and appends the "
            "automation event sequence. Image+CSV captures use one shared collision suffix. "
            "Other modes keep their existing output behavior."
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
            self.automation_condition_value_label = QLabel("--")
            self.automation_condition_state_label = QLabel("--")
            form.addRow("Condition value", self.automation_condition_value_label)
            form.addRow("Condition state", self.automation_condition_state_label)
        return card

    def _condition_operator_value(self) -> str:
        return str(self.automation_condition_operator.currentData())

    def _condition_operator_changed(self, *_args) -> None:
        range_operator = self._condition_operator_value() in {"inside", "outside"}
        self.automation_condition_high.setEnabled(range_operator)
        self._automation_update_recipe()

    def _condition_action_changed(self, *_args) -> None:
        self._sync_automation_actions_card()
        self._automation_update_recipe()

    def _conditional_config(self) -> ConditionalCaptureConfig:
        operator = self._condition_operator_value()
        high = self.automation_condition_high.value() if operator in {"inside", "outside"} else None
        return ConditionalCaptureConfig(
            slot=int(self.automation_condition_slot.currentData()),
            operator=operator,
            threshold=float(self.automation_condition_threshold.value()),
            high=high,
            consecutive_matches=int(self.automation_condition_debounce.value()),
            cooldown_s=float(self.automation_condition_cooldown.value()),
        )

    def _automation_mode_changed(self, *_args) -> None:
        super()._automation_mode_changed(*_args)
        row = getattr(self, "automation_condition_row", None)
        if row is not None:
            row.setVisible(self._automation_mode() == CONDITIONAL_CAPTURE_MODE)
        self._sync_automation_actions_card()
        self._automation_update_recipe()
        self._automation_refresh_status()

    def _sync_automation_actions_card(self) -> None:
        if self._automation_mode() != CONDITIONAL_CAPTURE_MODE:
            super()._sync_automation_actions_card()
            return
        action_combo = getattr(self, "automation_condition_action", None)
        action = ArtifactAction(action_combo.currentText()) if action_combo is not None else ArtifactAction.IMAGE
        image_box = getattr(self, "automation_save_image", None)
        csv_box = getattr(self, "automation_save_csv", None)
        hint = getattr(self, "automation_actions_hint", None)
        if image_box is not None:
            image_box.setChecked(action in {ArtifactAction.IMAGE, ArtifactAction.IMAGE_CSV})
        if csv_box is not None:
            csv_box.setChecked(action in {ArtifactAction.CSV, ArtifactAction.IMAGE_CSV})
        if hint is not None:
            hint.setText(
                "A6 saves artifacts only after the configured MEAS condition passes debounce "
                "and cooldown. Invalid reads never count as matches."
            )

    def _automation_update_recipe(self, *_args) -> None:
        if self._automation_mode() != CONDITIONAL_CAPTURE_MODE:
            super()._automation_update_recipe(*_args)
            return
        label = getattr(self, "automation_recipe_label", None)
        if label is None:
            return
        try:
            interval = PeriodicImageConfig(self._automation_interval_seconds())
            config = self._conditional_config()
            action = ArtifactAction(self.automation_condition_action.currentText())
        except Exception as exc:  # noqa: BLE001 - inline validation feedback.
            label.setText(f"Invalid configuration: {exc}")
            return
        operator_text = config.operator
        threshold_text = f"{config.threshold:g}"
        if config.operator in {"inside", "outside"}:
            threshold_text = f"[{config.threshold:g}, {config.high:g}]"
        label.setText(
            f"Every {interval.interval_s:g} seconds, read MEAS{config.slot}; when {operator_text} "
            f"{threshold_text} for {config.consecutive_matches} consecutive sample(s), save "
            f"{action.value}. Enforce {config.cooldown_s:g} s cooldown."
        )

    def _automation_refresh_status(self) -> None:
        super()._automation_refresh_status()
        if self._automation_mode() == CONDITIONAL_CAPTURE_MODE:
            mode_label = getattr(self, "automation_mode_label", None)
            if mode_label is not None:
                mode_label.setText(CONDITIONAL_CAPTURE_MODE)
        value_label = getattr(self, "automation_condition_value_label", None)
        state_label = getattr(self, "automation_condition_state_label", None)
        if value_label is not None:
            value_label.setText(
                "--" if self._conditional_last_value is None else f"{self._conditional_last_value:g}"
            )
        if state_label is not None:
            state_label.setText(self._conditional_last_state)

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
        controls = (
            "automation_condition_slot",
            "automation_condition_operator",
            "automation_condition_threshold",
            "automation_condition_debounce",
            "automation_condition_cooldown",
            "automation_condition_action",
        )
        for name in controls:
            control = getattr(self, name, None)
            if control is not None:
                control.setEnabled(editable)
        high = getattr(self, "automation_condition_high", None)
        if high is not None:
            high.setEnabled(editable and self._condition_operator_value() in {"inside", "outside"})

    def start_automation(self) -> None:
        if self._automation_mode() != CONDITIONAL_CAPTURE_MODE:
            super().start_automation()
            return
        self._start_conditional_capture()

    def run_automation_once(self) -> None:
        if self._automation_mode() != CONDITIONAL_CAPTURE_MODE:
            super().run_automation_once()
            return
        if not bool(getattr(self, "_connection_ok", False)):
            self._message("Automation", "Test the scope connection before running automation.", error=True)
            return
        if self._automation_controller.state is not AutomationState.IDLE:
            self._message("Automation", "Another periodic automation mode is active.", error=True)
            return
        if self._trigger_controller.state is not AutomationState.IDLE:
            self._message("Automation", "Trigger automation is already active.", error=True)
            return
        try:
            config = self._conditional_config()
            action = ArtifactAction(self.automation_condition_action.currentText())
        except Exception as exc:  # noqa: BLE001 - exact validation feedback.
            self._message("Automation", str(exc), error=True)
            return
        self._conditional_evaluator = ConditionalEvaluator(config)
        self._conditional_action_active = action
        self._conditional_last_value = None
        self._conditional_last_state = "Checking"
        self._automation_capture_condition(force=True)

    def _automation_tick(self) -> None:
        if self._automation_mode() == CONDITIONAL_CAPTURE_MODE:
            self._automation_capture_condition(force=False)
            return
        super()._automation_tick()

    def _start_conditional_capture(self) -> None:
        if not bool(getattr(self, "_connection_ok", False)):
            self._message("Automation", "Test the scope connection before starting automation.", error=True)
            return
        if self._trigger_controller.state is not AutomationState.IDLE:
            self._message("Automation", "Trigger automation is already active.", error=True)
            return
        try:
            interval = PeriodicImageConfig(self._automation_interval_seconds())
            config = self._conditional_config()
            action = ArtifactAction(self.automation_condition_action.currentText())
            self._ensure_control_page_built(FILE_PAGE_INDEX)
            self._automation_controller.start(interval)
        except Exception as exc:  # noqa: BLE001 - exact validation feedback.
            self._message("Automation", str(exc), error=True)
            return

        timer = self._automation_timer
        if timer is None:
            self._automation_controller.stop()
            self._message("Automation", "Automation timer is unavailable.", error=True)
            return
        self._conditional_evaluator = ConditionalEvaluator(config)
        self._conditional_action_active = action
        self._conditional_last_value = None
        self._conditional_last_state = "Waiting"
        self._automation_last_path = None
        self._automation_last_csv_path = None
        timer.setInterval(max(1, int(round(interval.interval_s * 1000.0))))
        timer.start()
        self._append_log(
            f"Automation A6 started: MEAS{config.slot} {config.operator}; "
            f"debounce {config.consecutive_matches}, cooldown {config.cooldown_s:g} s"
        )
        self.statusBar().showMessage("Automation running: conditional capture")
        self._automation_refresh_status()

    def _build_conditional_paths(
        self,
        sequence: int,
        action: ArtifactAction,
    ) -> tuple[Path | None, Path | None]:
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        timestamp = datetime.now()
        image_path: Path | None = None
        csv_path: Path | None = None
        if action in {ArtifactAction.IMAGE, ArtifactAction.IMAGE_CSV}:
            image_naming = FileNaming(
                prefix=self.png_prefix.text(),
                base=self.png_base.text(),
                extension="png",
                fallback="screen",
                add_timestamp=self.png_timestamp.isChecked(),
            )
            image_path = append_sequence(
                build_output_path(self.output_folder.text(), image_naming, timestamp=timestamp),
                sequence,
            )
        if action in {ArtifactAction.CSV, ArtifactAction.IMAGE_CSV}:
            csv_naming = FileNaming(
                prefix=self.csv_prefix.text(),
                base=self.csv_base.text(),
                extension="csv",
                fallback="waveform",
                add_timestamp=self.csv_timestamp.isChecked(),
            )
            csv_path = append_sequence(
                build_output_path(self.output_folder.text(), csv_naming, timestamp=timestamp),
                sequence,
            )
        if image_path is not None and csv_path is not None:
            return collision_safe_bundle_paths(image_path, csv_path)
        if image_path is not None:
            image_path = collision_safe_path(image_path)
        if csv_path is not None:
            csv_path = collision_safe_path(csv_path)
        return image_path, csv_path

    def _automation_capture_condition(self, *, force: bool) -> None:
        token = self._automation_controller.begin_event(force=force)
        if token is None:
            self._automation_refresh_status()
            return
        evaluator = self._conditional_evaluator
        if evaluator is None:
            self._automation_controller.finish_event(
                token,
                success=False,
                error="Conditional evaluator is unavailable.",
            )
            self._automation_refresh_status()
            return
        action = self._conditional_action_active
        try:
            image_path, csv_path = self._build_conditional_paths(token.sequence, action)
            for path in (image_path, csv_path):
                if path is not None:
                    path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001 - output validation failure.
            self._automation_controller.finish_event(token, success=False, error=str(exc))
            self._append_log(f"Automation A6 output error: {exc}")
            self.stop_automation()
            return

        result = self._run_action(
            f"Evaluating conditional capture #{token.sequence:04d}",
            lambda scope: run_conditional_poll(
                scope,
                evaluator,
                now_s=time.monotonic(),
                action=action,
                image_path=str(image_path) if image_path is not None else None,
                csv_path=str(csv_path) if csv_path is not None else None,
            ),
        )
        if not isinstance(result, ConditionalPollResult):
            self._automation_controller.finish_event(
                token,
                success=False,
                error=str(getattr(self, "_last_action", "Conditional capture failed")),
            )
            self.stop_automation()
            return

        evaluation = result.evaluation
        self._conditional_last_value = evaluation.value
        if not evaluation.valid:
            self._conditional_last_state = f"Invalid: {evaluation.error}"
            self._automation_controller.finish_skipped(token, reason=evaluation.error)
            self._automation_refresh_status()
            return
        if not evaluation.fire:
            if evaluation.matched:
                self._conditional_last_state = (
                    f"Matched; debounce/cooldown pending ({evaluation.streak})"
                )
            else:
                self._conditional_last_state = "No match"
            self._automation_controller.finish_skipped(token)
            self._automation_refresh_status()
            return

        artifacts = result.artifacts
        if artifacts is None or not artifacts.success:
            error = artifacts.error if artifacts is not None else "Conditional artifacts were not saved"
            self._conditional_last_state = f"Capture failed: {error}"
            self._automation_controller.finish_event(token, success=False, error=error)
            self._append_log(f"Automation A6 failed: {error}")
            self.stop_automation()
            return

        self._conditional_last_state = "Captured"
        if self._automation_controller.finish_event(token, success=True):
            if artifacts.image_path is not None:
                self._automation_last_path = Path(artifacts.image_path)
                self._last_image_path = Path(artifacts.image_path)
            if artifacts.csv_path is not None:
                self._automation_last_csv_path = Path(artifacts.csv_path)
                if artifacts.image_path is None:
                    self._automation_last_path = Path(artifacts.csv_path)
            self._append_log(
                f"A6 capture #{token.sequence:04d}: value {evaluation.value:g}, {action.value}"
            )
            self.statusBar().showMessage(
                f"Conditional capture saved: #{token.sequence:04d} ({evaluation.value:g})"
            )
        self._automation_refresh_status()


__all__ = ["CONDITIONAL_CAPTURE_MODE", "QtScopeWindow"]
