"""A4 Timed Waveform Logging automation UI."""

from __future__ import annotations

from pathlib import Path

from ..automation import (
    AutomationState,
    PeriodicImageConfig,
    TimedWaveformResult,
    append_sequence,
    collision_safe_path,
    save_full_record_csv,
)
from ..gui.config import FileNaming, build_output_path
from .automation_trigger_bundle_window import (
    TRIGGER_IMAGE_CSV_MODE,
    QtScopeWindow as AutomationA3QtScopeWindow,
)
from .automation_trigger_window import PERIODIC_IMAGE_MODE, TRIGGER_IMAGE_MODE
from .automation_window import FILE_PAGE_INDEX

TIMED_WAVEFORM_MODE = "Timed Waveform Logging"


class QtScopeWindow(AutomationA3QtScopeWindow):
    """A3 window extended with periodic full-record CSV capture."""

    def _build_automation_mode_card(self):
        card = super()._build_automation_mode_card()
        if self.automation_mode_combo.findText(TIMED_WAVEFORM_MODE) < 0:
            self.automation_mode_combo.addItem(TIMED_WAVEFORM_MODE)
        return card

    def _sync_automation_actions_card(self) -> None:
        mode = self._automation_mode()
        image_box = getattr(self, "automation_save_image", None)
        csv_box = getattr(self, "automation_save_csv", None)
        hint = getattr(self, "automation_actions_hint", None)
        if image_box is not None:
            image_box.setChecked(mode != TIMED_WAVEFORM_MODE)
        if csv_box is not None:
            csv_box.setChecked(mode in {TRIGGER_IMAGE_CSV_MODE, TIMED_WAVEFORM_MODE})
        if hint is None:
            return
        if mode == TIMED_WAVEFORM_MODE:
            hint.setText(
                "A4 periodically saves one full enabled-channel CSV record without taking a screenshot."
            )
        elif mode == TRIGGER_IMAGE_CSV_MODE:
            hint.setText(
                "A3 saves PNG and full enabled-channel CSV before the next Single acquisition is armed."
            )
        elif mode == TRIGGER_IMAGE_MODE:
            hint.setText("A2 saves one PNG after each completed Single acquisition.")
        else:
            hint.setText("A1 periodically saves PNG images.")

    def _automation_update_recipe(self, *_args) -> None:
        if self._automation_mode() != TIMED_WAVEFORM_MODE:
            super()._automation_update_recipe(*_args)
            return
        label = getattr(self, "automation_recipe_label", None)
        if label is None:
            return
        try:
            config = PeriodicImageConfig(self._automation_interval_seconds())
        except Exception as exc:  # noqa: BLE001 - inline validation feedback.
            label.setText(f"Invalid configuration: {exc}")
            return
        label.setText(
            f"Every {config.interval_s:g} seconds, save one full enabled-channel CSV record. "
            "Do not capture a PNG image."
        )

    def _automation_refresh_status(self) -> None:
        super()._automation_refresh_status()
        if self._automation_mode() == TIMED_WAVEFORM_MODE:
            mode_label = getattr(self, "automation_mode_label", None)
            if mode_label is not None:
                mode_label.setText(TIMED_WAVEFORM_MODE)

    def start_automation(self) -> None:
        if self._automation_mode() != TIMED_WAVEFORM_MODE:
            super().start_automation()
            return
        self._start_timed_waveform_automation()

    def run_automation_once(self) -> None:
        if self._automation_mode() != TIMED_WAVEFORM_MODE:
            super().run_automation_once()
            return
        if not bool(getattr(self, "_connection_ok", False)):
            self._message("Automation", "Test the scope connection before running automation.", error=True)
            return
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        self._automation_capture_csv(force=True)

    def _automation_tick(self) -> None:
        if self._automation_mode() == TIMED_WAVEFORM_MODE:
            self._automation_capture_csv(force=False)
            return
        super()._automation_tick()

    def _start_timed_waveform_automation(self) -> None:
        if not bool(getattr(self, "_connection_ok", False)):
            self._message("Automation", "Test the scope connection before starting automation.", error=True)
            return
        if self._trigger_controller.state is not AutomationState.IDLE:
            self._message("Automation", "Trigger automation is already active.", error=True)
            return
        try:
            config = PeriodicImageConfig(self._automation_interval_seconds())
            self._ensure_control_page_built(FILE_PAGE_INDEX)
            self._automation_controller.start(config)
        except Exception as exc:  # noqa: BLE001 - exact validation feedback.
            self._message("Automation", str(exc), error=True)
            return

        timer = self._automation_timer
        if timer is None:
            self._automation_controller.stop()
            self._message("Automation", "Automation timer is unavailable.", error=True)
            return
        timer.setInterval(max(1, int(round(config.interval_s * 1000.0))))
        timer.start()
        self._automation_last_csv_path = None
        self._append_log(
            f"Automation A4 started: full-record CSV every {config.interval_s:g} s"
        )
        self.statusBar().showMessage(
            f"Automation running: waveform CSV every {config.interval_s:g} s"
        )
        self._automation_refresh_status()

    def _automation_build_csv_path(self, sequence: int) -> Path:
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        naming = FileNaming(
            prefix=self.csv_prefix.text(),
            base=self.csv_base.text(),
            extension="csv",
            fallback="waveform",
            add_timestamp=self.csv_timestamp.isChecked(),
        )
        path = build_output_path(self.output_folder.text(), naming)
        return collision_safe_path(append_sequence(path, sequence))

    def _automation_capture_csv(self, *, force: bool) -> None:
        token = self._automation_controller.begin_event(force=force)
        if token is None:
            self._automation_refresh_status()
            return

        try:
            path = self._automation_build_csv_path(token.sequence)
            path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001 - output validation failure.
            self._automation_controller.finish_event(token, success=False, error=str(exc))
            self._append_log(f"Automation A4 output error: {exc}")
            self._stop_timed_waveform_after_failure()
            return

        result = self._run_action(
            f"Automation waveform CSV #{token.sequence:04d}",
            lambda scope: save_full_record_csv(scope, path),
        )
        if isinstance(result, TimedWaveformResult) and result.success:
            accepted = self._automation_controller.finish_event(token, success=True)
            if accepted and result.csv_path is not None:
                saved_path = Path(result.csv_path)
                self._automation_last_csv_path = saved_path
                self._automation_last_path = saved_path
                self.statusBar().showMessage(
                    f"Automation waveform CSV saved: {saved_path.name} ({result.point_count} points)"
                )
        else:
            error = (
                result.error
                if isinstance(result, TimedWaveformResult) and result.error
                else str(getattr(self, "_last_action", "Waveform CSV capture failed"))
            )
            self._automation_controller.finish_event(token, success=False, error=error)
            self._append_log(f"Automation A4 failed: {error}")
            self._stop_timed_waveform_after_failure()
            return
        self._automation_refresh_status()

    def _stop_timed_waveform_after_failure(self) -> None:
        timer = self._automation_timer
        if timer is not None:
            timer.stop()
        self._automation_controller.stop()
        self._automation_refresh_status()


__all__ = ["TIMED_WAVEFORM_MODE", "QtScopeWindow"]
