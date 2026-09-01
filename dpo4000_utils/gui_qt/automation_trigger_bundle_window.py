"""A3 Image + CSV on Trigger automation UI.

A3 extends the reviewed A2 trigger workflow with an evidence bundle that saves a
screen image and enabled-channel waveform CSV from the same completed Single
acquisition. Scope I/O remains in the framework-neutral automation helper and
public driver API.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import Event

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QCheckBox, QFormLayout, QLabel, QVBoxLayout

from ..automation import (
    AutomationState,
    TriggerBundleResult,
    TriggerImageConfig,
    acquire_trigger_bundle,
    append_sequence,
    collision_safe_path,
)
from ..gui.config import FileNaming, build_output_path
from .automation_trigger_review_window import QtScopeWindow as AutomationA2ReviewedQtScopeWindow
from .automation_trigger_window import PERIODIC_IMAGE_MODE, TRIGGER_IMAGE_MODE
from .automation_window import FILE_PAGE_INDEX

TRIGGER_IMAGE_CSV_MODE = "Image + CSV on Trigger"


class QtScopeWindow(AutomationA2ReviewedQtScopeWindow):
    """Reviewed A2 window extended with A3 same-acquisition image + CSV bundles."""

    def __init__(self, *args, **kwargs) -> None:
        self._automation_last_csv_path: Path | None = None
        super().__init__(*args, **kwargs)

    # ------------------------------------------------------------------
    # Mode and action presentation
    # ------------------------------------------------------------------
    def _build_automation_mode_card(self):
        card = super()._build_automation_mode_card()
        if self.automation_mode_combo.findText(TRIGGER_IMAGE_CSV_MODE) < 0:
            self.automation_mode_combo.addItem(TRIGGER_IMAGE_CSV_MODE)
        return card

    def _build_automation_actions_card(self):
        card = self._card("Actions")
        layout = QVBoxLayout(card)
        self.automation_save_image = QCheckBox("Save PNG image")
        self.automation_save_image.setChecked(True)
        self.automation_save_image.setEnabled(False)
        self.automation_save_csv = QCheckBox("Save enabled-channel CSV")
        self.automation_save_csv.setChecked(False)
        self.automation_save_csv.setEnabled(False)
        self.automation_actions_hint = QLabel("")
        self.automation_actions_hint.setObjectName("MutedLabel")
        self.automation_actions_hint.setWordWrap(True)
        layout.addWidget(self.automation_save_image)
        layout.addWidget(self.automation_save_csv)
        layout.addWidget(self.automation_actions_hint)
        self._sync_automation_actions_card()
        return self._prepare_drawer_card(card)

    def _build_automation_output_card(self):
        card = self._card("Output & Retention")
        layout = QVBoxLayout(card)
        label = QLabel(
            "Uses File → Destination folder plus the configured PNG and CSV naming settings. "
            "Automation appends one shared four-digit event sequence and allocates collision-safe "
            "paths instead of silently overwriting files."
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
            self.automation_last_csv_label = QLabel("--")
            self.automation_last_csv_label.setWordWrap(True)
            form.addRow("Last CSV", self.automation_last_csv_label)
        return card

    def _automation_mode_changed(self, *_args) -> None:
        super()._automation_mode_changed(*_args)
        mode = self._automation_mode()
        trigger_mode = mode in {TRIGGER_IMAGE_MODE, TRIGGER_IMAGE_CSV_MODE}
        periodic_row = getattr(self, "automation_periodic_row", None)
        trigger_row = getattr(self, "automation_trigger_row", None)
        if periodic_row is not None:
            periodic_row.setVisible(not trigger_mode)
        if trigger_row is not None:
            trigger_row.setVisible(trigger_mode)
        rearm = getattr(self, "automation_trigger_rearm", None)
        if rearm is not None:
            rearm.setText(
                "Re-arm Single after each saved image + CSV"
                if mode == TRIGGER_IMAGE_CSV_MODE
                else "Re-arm Single after each saved image"
            )
        self._sync_automation_actions_card()
        self._automation_update_recipe()
        self._automation_refresh_status()

    def _sync_automation_actions_card(self) -> None:
        mode = self._automation_mode()
        csv_box = getattr(self, "automation_save_csv", None)
        hint = getattr(self, "automation_actions_hint", None)
        if csv_box is not None:
            csv_box.setChecked(mode == TRIGGER_IMAGE_CSV_MODE)
        if hint is None:
            return
        if mode == TRIGGER_IMAGE_CSV_MODE:
            hint.setText(
                "A3 saves PNG and full enabled-channel CSV before the next Single acquisition is armed."
            )
        elif mode == TRIGGER_IMAGE_MODE:
            hint.setText("A2 saves one PNG after each completed Single acquisition.")
        else:
            hint.setText("A1 periodically saves PNG images.")

    def _automation_update_recipe(self, *_args) -> None:
        if self._automation_mode() != TRIGGER_IMAGE_CSV_MODE:
            super()._automation_update_recipe(*_args)
            return
        label = getattr(self, "automation_recipe_label", None)
        if label is None:
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
            "Arm a Single acquisition, wait for completion, save PNG and full enabled-channel CSV "
            f"from that same acquisition, {rearm}. Poll interval {config.poll_interval_s:g} s."
        )

    def _automation_refresh_status(self) -> None:
        super()._automation_refresh_status()
        mode = self._automation_mode()
        trigger = getattr(self, "_trigger_controller", None)
        if trigger is not None and mode == TRIGGER_IMAGE_CSV_MODE:
            mode_label = getattr(self, "automation_mode_label", None)
            if mode_label is not None:
                mode_label.setText(TRIGGER_IMAGE_CSV_MODE)
        csv_label = getattr(self, "automation_last_csv_label", None)
        if csv_label is not None:
            csv_label.setText(
                str(self._automation_last_csv_path) if self._automation_last_csv_path else "--"
            )

    # ------------------------------------------------------------------
    # Mode dispatch
    # ------------------------------------------------------------------
    def start_automation(self) -> None:
        if self._automation_mode() != TRIGGER_IMAGE_CSV_MODE:
            super().start_automation()
            return
        self._start_trigger_bundle_automation(rearm=self.automation_trigger_rearm.isChecked())

    def run_automation_once(self) -> None:
        if self._automation_mode() != TRIGGER_IMAGE_CSV_MODE:
            super().run_automation_once()
            return
        self._start_trigger_bundle_automation(rearm=False)

    def pause_resume_automation(self) -> None:
        if self._automation_mode() != TRIGGER_IMAGE_CSV_MODE:
            super().pause_resume_automation()
            return
        trigger = self._trigger_controller
        if trigger.state is AutomationState.RUNNING:
            trigger.pause()
            cancel = self._trigger_cancel_event
            if cancel is not None:
                cancel.set()
            self._append_log("Image + CSV trigger automation paused; current Single acquisition cancelled")
            self._automation_refresh_status()
            return
        if trigger.state is AutomationState.PAUSED:
            trigger.resume()
            self._append_log("Image + CSV trigger automation resumed")
            self._automation_refresh_status()
            QTimer.singleShot(0, self._trigger_bundle_cycle)
            return
        super().pause_resume_automation()

    # ------------------------------------------------------------------
    # A3 trigger bundle cycle
    # ------------------------------------------------------------------
    def _start_trigger_bundle_automation(self, *, rearm: bool) -> None:
        if not bool(getattr(self, "_connection_ok", False)):
            self._message("Automation", "Test the scope connection before starting automation.", error=True)
            return
        if self._automation_controller.state is not AutomationState.IDLE:
            self._message("Automation", "Periodic automation is already active.", error=True)
            return
        try:
            config = TriggerImageConfig(
                poll_interval_s=float(self.automation_trigger_poll.value()),
                rearm=bool(rearm),
            )
            self._ensure_control_page_built(FILE_PAGE_INDEX)
            self._trigger_controller.start(config)
        except Exception as exc:  # noqa: BLE001 - exact validation feedback.
            self._message("Automation", str(exc), error=True)
            return

        self._trigger_last_state = "ARMING"
        self._automation_last_csv_path = None
        self._append_log(
            f"Automation A3 started: Single -> wait -> image + CSV; poll {config.poll_interval_s:g} s"
        )
        self._automation_refresh_status()
        QTimer.singleShot(0, self._trigger_bundle_cycle)

    def _automation_build_bundle_paths(self, sequence: int) -> tuple[Path, Path]:
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        timestamp = datetime.now()
        image_naming = FileNaming(
            prefix=self.png_prefix.text(),
            base=self.png_base.text(),
            extension="png",
            fallback="screen",
            add_timestamp=self.png_timestamp.isChecked(),
        )
        csv_naming = FileNaming(
            prefix=self.csv_prefix.text(),
            base=self.csv_base.text(),
            extension="csv",
            fallback="waveform",
            add_timestamp=self.csv_timestamp.isChecked(),
        )
        image_path = build_output_path(self.output_folder.text(), image_naming, timestamp=timestamp)
        csv_path = build_output_path(self.output_folder.text(), csv_naming, timestamp=timestamp)
        return (
            collision_safe_path(append_sequence(image_path, sequence)),
            collision_safe_path(append_sequence(csv_path, sequence)),
        )

    def _trigger_bundle_cycle(self) -> None:
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

        try:
            image_path, csv_path = self._automation_build_bundle_paths(token.sequence)
            image_path.parent.mkdir(parents=True, exist_ok=True)
            csv_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001 - file validation failure.
            trigger.finish_cycle(token, success=False, error=str(exc))
            trigger.stop()
            self._append_log(f"Automation A3 output error: {exc}")
            self._automation_refresh_status()
            return

        cancel = Event()
        self._trigger_cancel_event = cancel
        self._trigger_last_state = "ARMED"
        self._automation_refresh_status()

        result = self._run_action(
            f"Capturing triggered image + CSV #{token.sequence:04d}",
            lambda scope: acquire_trigger_bundle(
                scope,
                cancel,
                poll_interval_s=config.poll_interval_s,
                image_path=image_path,
                csv_path=csv_path,
            ),
        )
        self._trigger_cancel_event = None

        if token.generation != trigger.generation:
            return
        if trigger.state is not AutomationState.RUNNING:
            trigger.cancel_cycle(token)
            self._automation_refresh_status()
            return
        if not isinstance(result, TriggerBundleResult):
            partial = []
            if image_path.exists():
                partial.append(image_path.name)
            if csv_path.exists():
                partial.append(csv_path.name)
            detail = f"; partial artifacts: {', '.join(partial)}" if partial else ""
            trigger.finish_cycle(token, success=False, error=f"Image + CSV capture failed{detail}")
            trigger.stop()
            self._append_log(f"Automation A3 failed{detail}")
            self._automation_refresh_status()
            return

        self._trigger_last_state = result.trigger_state or self._trigger_last_state
        if result.cancelled:
            trigger.cancel_cycle(token)
            self._automation_refresh_status()
            return
        if not result.completed or result.image_path is None or result.csv_path is None:
            trigger.finish_cycle(token, success=False, error="Single acquisition bundle did not complete")
            trigger.stop()
            self._automation_refresh_status()
            return

        if trigger.finish_cycle(token, success=True):
            self._automation_last_path = Path(result.image_path)
            self._automation_last_csv_path = Path(result.csv_path)
            self._last_image_path = Path(result.image_path)
            self._append_log(
                f"A3 bundle #{token.sequence:04d}: {Path(result.image_path).name}, "
                f"{Path(result.csv_path).name}, {result.point_count} points"
            )
            self.statusBar().showMessage(
                f"Triggered image + CSV saved: #{token.sequence:04d} ({result.point_count} points)"
            )

        if trigger.state is not AutomationState.RUNNING:
            self._automation_refresh_status()
            return
        if config.rearm:
            QTimer.singleShot(0, self._trigger_bundle_cycle)
        else:
            trigger.stop()
        self._automation_refresh_status()


__all__ = ["TRIGGER_IMAGE_CSV_MODE", "QtScopeWindow"]
