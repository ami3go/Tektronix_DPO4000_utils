"""A5 Measurement Logger automation UI."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QFormLayout, QGridLayout, QLabel, QVBoxLayout, QWidget

from ..automation import (
    AutomationState,
    MeasurementLogResult,
    PeriodicImageConfig,
    append_measurement_row,
    collision_safe_path,
    normalize_measurement_slots,
)
from ..gui.config import FileNaming, build_output_path
from .automation_waveform_window import (
    TIMED_WAVEFORM_MODE,
    QtScopeWindow as AutomationA4QtScopeWindow,
)
from .automation_window import FILE_PAGE_INDEX

MEASUREMENT_LOGGER_MODE = "Measurement Logger"


class QtScopeWindow(AutomationA4QtScopeWindow):
    """A4 window extended with periodic MEAS1..MEAS8 CSV logging."""

    def __init__(self, *args, **kwargs) -> None:
        self._measurement_log_path: Path | None = None
        self._measurement_slots_active: tuple[int, ...] = ()
        self._measurement_run_started_utc: datetime | None = None
        super().__init__(*args, **kwargs)

    def _build_automation_mode_card(self):
        card = super()._build_automation_mode_card()
        if self.automation_mode_combo.findText(MEASUREMENT_LOGGER_MODE) < 0:
            self.automation_mode_combo.addItem(MEASUREMENT_LOGGER_MODE)

        form = card.layout()
        self.automation_measurement_row = QWidget()
        grid = QGridLayout(self.automation_measurement_row)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(6)
        self.automation_measurement_slots: dict[int, QCheckBox] = {}
        for offset, slot in enumerate(range(1, 9)):
            checkbox = QCheckBox(f"MEAS{slot}")
            checkbox.setChecked(True)
            checkbox.toggled.connect(self._automation_update_recipe)
            self.automation_measurement_slots[slot] = checkbox
            grid.addWidget(checkbox, offset // 4, offset % 4)
        self.automation_measurement_row.setVisible(False)
        if isinstance(form, QFormLayout):
            form.addRow("Measurements", self.automation_measurement_row)
        return card

    def _build_automation_output_card(self):
        card = self._card("Output & Retention")
        layout = QVBoxLayout(card)
        label = QLabel(
            "Periodic Image uses PNG naming. Timed Waveform Logging creates one CSV per interval. "
            "Measurement Logger appends all selected MEAS values to one CSV per run. Trigger "
            "bundles use matched PNG + CSV names."
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        hint = QLabel("Retention is added in A9.")
        hint.setObjectName("MutedLabel")
        layout.addWidget(hint)
        return self._prepare_drawer_card(card)

    def _automation_mode_changed(self, *_args) -> None:
        super()._automation_mode_changed(*_args)
        row = getattr(self, "automation_measurement_row", None)
        if row is not None:
            row.setVisible(self._automation_mode() == MEASUREMENT_LOGGER_MODE)
        self._sync_automation_actions_card()
        self._automation_update_recipe()
        self._automation_refresh_status()

    def _sync_automation_actions_card(self) -> None:
        if self._automation_mode() != MEASUREMENT_LOGGER_MODE:
            super()._sync_automation_actions_card()
            return
        image_box = getattr(self, "automation_save_image", None)
        csv_box = getattr(self, "automation_save_csv", None)
        hint = getattr(self, "automation_actions_hint", None)
        if image_box is not None:
            image_box.setChecked(False)
        if csv_box is not None:
            csv_box.setChecked(True)
        if hint is not None:
            hint.setText(
                "A5 appends timestamped MEAS values to one fixed-column CSV for the whole run."
            )

    def _selected_measurement_slots(self) -> tuple[int, ...]:
        boxes = getattr(self, "automation_measurement_slots", {})
        return normalize_measurement_slots(
            slot for slot, checkbox in boxes.items() if checkbox.isChecked()
        )

    def _automation_update_recipe(self, *_args) -> None:
        if self._automation_mode() != MEASUREMENT_LOGGER_MODE:
            super()._automation_update_recipe(*_args)
            return
        label = getattr(self, "automation_recipe_label", None)
        if label is None:
            return
        try:
            config = PeriodicImageConfig(self._automation_interval_seconds())
            slots = self._selected_measurement_slots()
        except Exception as exc:  # noqa: BLE001 - inline validation feedback.
            label.setText(f"Invalid configuration: {exc}")
            return
        slot_text = ", ".join(f"MEAS{slot}" for slot in slots)
        label.setText(
            f"Every {config.interval_s:g} seconds, append {slot_text} to one measurement CSV."
        )

    def _automation_refresh_status(self) -> None:
        super()._automation_refresh_status()
        if self._automation_mode() == MEASUREMENT_LOGGER_MODE:
            mode_label = getattr(self, "automation_mode_label", None)
            if mode_label is not None:
                mode_label.setText(MEASUREMENT_LOGGER_MODE)
        periodic_active = self._automation_controller.state in {
            AutomationState.RUNNING,
            AutomationState.PAUSED,
        }
        trigger_active = self._trigger_controller.state in {
            AutomationState.RUNNING,
            AutomationState.PAUSED,
        }
        for checkbox in getattr(self, "automation_measurement_slots", {}).values():
            checkbox.setEnabled(not periodic_active and not trigger_active)

    def start_automation(self) -> None:
        if self._automation_mode() != MEASUREMENT_LOGGER_MODE:
            super().start_automation()
            return
        self._start_measurement_logger()

    def run_automation_once(self) -> None:
        if self._automation_mode() != MEASUREMENT_LOGGER_MODE:
            super().run_automation_once()
            return
        if not bool(getattr(self, "_connection_ok", False)):
            self._message("Automation", "Test the scope connection before running automation.", error=True)
            return
        try:
            slots = self._selected_measurement_slots()
            path = self._build_measurement_log_path()
        except Exception as exc:  # noqa: BLE001 - configuration/output feedback.
            self._message("Automation", str(exc), error=True)
            return
        self._measurement_slots_active = slots
        self._measurement_log_path = path
        self._measurement_run_started_utc = datetime.now(timezone.utc)
        self._automation_last_path = None
        self._automation_last_csv_path = None
        self._automation_capture_measurements(force=True)

    def _automation_tick(self) -> None:
        if self._automation_mode() == MEASUREMENT_LOGGER_MODE:
            self._automation_capture_measurements(force=False)
            return
        super()._automation_tick()

    def _start_measurement_logger(self) -> None:
        if not bool(getattr(self, "_connection_ok", False)):
            self._message("Automation", "Test the scope connection before starting automation.", error=True)
            return
        if self._trigger_controller.state is not AutomationState.IDLE:
            self._message("Automation", "Trigger automation is already active.", error=True)
            return
        try:
            config = PeriodicImageConfig(self._automation_interval_seconds())
            slots = self._selected_measurement_slots()
            path = self._build_measurement_log_path()
            self._automation_controller.start(config)
        except Exception as exc:  # noqa: BLE001 - exact validation feedback.
            self._message("Automation", str(exc), error=True)
            return

        timer = self._automation_timer
        if timer is None:
            self._automation_controller.stop()
            self._message("Automation", "Automation timer is unavailable.", error=True)
            return
        self._measurement_slots_active = slots
        self._measurement_log_path = path
        self._measurement_run_started_utc = datetime.now(timezone.utc)
        self._automation_last_path = None
        self._automation_last_csv_path = None
        timer.setInterval(max(1, int(round(config.interval_s * 1000.0))))
        timer.start()
        self._append_log(
            f"Automation A5 started: {len(slots)} measurement slots every {config.interval_s:g} s"
        )
        self.statusBar().showMessage(
            f"Automation running: measurement logger every {config.interval_s:g} s"
        )
        self._automation_refresh_status()

    def _build_measurement_log_path(self) -> Path:
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        configured_base = self.csv_base.text().strip() or "measurements"
        naming = FileNaming(
            prefix=self.csv_prefix.text(),
            base=f"{configured_base}_measurements",
            extension="csv",
            fallback="measurements",
            add_timestamp=self.csv_timestamp.isChecked(),
        )
        path = collision_safe_path(build_output_path(self.output_folder.text(), naming))
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _automation_capture_measurements(self, *, force: bool) -> None:
        token = self._automation_controller.begin_event(force=force)
        if token is None:
            self._automation_refresh_status()
            return
        path = self._measurement_log_path
        started = self._measurement_run_started_utc
        slots = self._measurement_slots_active
        if path is None or started is None or not slots:
            self._automation_controller.finish_event(
                token,
                success=False,
                error="Measurement logger run state is incomplete.",
            )
            self._stop_measurement_logger_after_failure()
            return

        result = self._run_action(
            f"Logging measurement row #{token.sequence:04d}",
            lambda scope: append_measurement_row(
                scope,
                path,
                slots,
                run_started_utc=started,
            ),
        )
        if isinstance(result, MeasurementLogResult) and result.success:
            accepted = self._automation_controller.finish_event(token, success=True)
            if accepted and result.csv_path is not None:
                saved_path = Path(result.csv_path)
                self._automation_last_path = saved_path
                self._automation_last_csv_path = saved_path
                if result.slot_errors:
                    detail = ", ".join(
                        f"MEAS{slot}: {error}" for slot, error in result.slot_errors.items()
                    )
                    self._append_log(f"Measurement logger row has unavailable values: {detail}")
                self.statusBar().showMessage(
                    f"Measurement row appended: {saved_path.name} (row {token.sequence})"
                )
        else:
            error = (
                result.error
                if isinstance(result, MeasurementLogResult) and result.error
                else str(getattr(self, "_last_action", "Measurement logging failed"))
            )
            self._automation_controller.finish_event(token, success=False, error=error)
            self._append_log(f"Automation A5 failed: {error}")
            self._stop_measurement_logger_after_failure()
            return
        self._automation_refresh_status()

    def _stop_measurement_logger_after_failure(self) -> None:
        timer = self._automation_timer
        if timer is not None:
            timer.stop()
        self._automation_controller.stop()
        self._automation_refresh_status()


__all__ = ["MEASUREMENT_LOGGER_MODE", "QtScopeWindow"]
