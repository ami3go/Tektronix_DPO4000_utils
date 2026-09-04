"""A1 Periodic Image automation tab for the launched DPO4000 Desk GUI.

This layer intentionally contains no Tektronix SCPI or PyVISA calls.  Periodic
captures are routed through the existing serialized ``_run_action`` gateway and
the public driver ``save_image_path`` API.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..automation import (
    AutomationState,
    PeriodicImageConfig,
    PeriodicImageController,
    append_sequence,
    collision_safe_path,
)
from ..gui.config import FileNaming, build_output_path
from . import collapsible_window as _collapsible_window
from . import display_window as _display_window

AUTOMATION_PAGE_INDEX = 5
FILE_PAGE_INDEX = 6
DISPLAY_PAGE_INDEX = 7
LOG_PAGE_INDEX = 8
CONTROL_TAB_TITLES = (
    "Connection",
    "Channels",
    "Measurement",
    "Trigger",
    "Acquisition",
    "Automation",
    "File",
    "Display",
    "Log",
)
CONTROL_PAGE_BUILDERS = (
    "_build_connection_tab",
    "_build_channels_tab",
    "_build_measurement_tab",
    "_build_trigger_tab",
    "_build_acquisition_tab",
    "_build_automation_tab",
    "_build_file_tab",
    "_build_display_tab",
    "_build_log_tab",
)
PAGE_SHORTCUTS = tuple(
    (f"Ctrl+{index + 1}", index, title)
    for index, title in enumerate(CONTROL_TAB_TITLES)
)

# Centralize the inserted page for the existing display-window implementation.
# The methods in those modules resolve their module globals at runtime, while the
# File page index imported by ui_polish_window is captured below after this patch.
_display_window.CONTROL_TAB_TITLES = CONTROL_TAB_TITLES
_display_window.CONTROL_PAGE_BUILDERS = CONTROL_PAGE_BUILDERS
_display_window.DISPLAY_PAGE_SHORTCUTS = PAGE_SHORTCUTS
_display_window.FILE_PAGE_INDEX = FILE_PAGE_INDEX
_display_window.DISPLAY_PAGE_INDEX = DISPLAY_PAGE_INDEX
_display_window.LOG_PAGE_INDEX = LOG_PAGE_INDEX
_collapsible_window.SETTINGS_PAGE_INDEX = FILE_PAGE_INDEX
_collapsible_window.PREFERENCE_PAGE_INDEXES = (
    _collapsible_window.CONNECTION_PAGE_INDEX,
    _collapsible_window.TRIGGER_PAGE_INDEX,
    FILE_PAGE_INDEX,
)

from .ui_polish_window import QtScopeWindow as UiPolishQtScopeWindow  # noqa: E402
from . import titlebar_tabs_window as _titlebar_tabs_window  # noqa: E402

_titlebar_tabs_window.CONTROL_TAB_TITLES = CONTROL_TAB_TITLES

_INTERVAL_FACTORS = {
    "seconds": 1.0,
    "minutes": 60.0,
    "hours": 3600.0,
}


class QtScopeWindow(UiPolishQtScopeWindow):
    """Launched window with Automation A1: periodic scope-image capture."""

    def __init__(self, *args, **kwargs) -> None:
        self._automation_controller = PeriodicImageController()
        self._automation_last_path: Path | None = None
        self._automation_timer: QTimer | None = None
        super().__init__(*args, **kwargs)
        self._automation_timer = QTimer(self)
        self._automation_timer.setSingleShot(False)
        self._automation_timer.timeout.connect(self._automation_tick)

    # ------------------------------------------------------------------
    # Automation page
    # ------------------------------------------------------------------
    def _build_automation_tab(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(12)

        layout.addWidget(self._build_automation_status_card())
        layout.addWidget(self._build_automation_mode_card())
        layout.addWidget(self._build_automation_actions_card())
        layout.addWidget(self._build_automation_run_limits_card())
        layout.addWidget(self._build_automation_output_card())
        layout.addWidget(self._build_automation_reliability_card())
        layout.addWidget(self._build_automation_current_run_card())
        layout.addStretch(1)
        self._automation_refresh_status()
        self._automation_update_recipe()
        return self._wrap_scrollable_drawer_page(
            body,
            scroll_name="AutomationScrollArea",
            body_name="AutomationScrollBody",
        )

    def _build_automation_status_card(self):
        card = self._card("Status & Control")
        form = QFormLayout(card)
        self._prepare_form(form)

        self.automation_state_label = QLabel("Idle")
        self.automation_mode_label = QLabel("Periodic Image")
        self.automation_recipe_label = QLabel("")
        self.automation_recipe_label.setObjectName("MutedLabel")
        self.automation_recipe_label.setWordWrap(True)
        form.addRow("State", self.automation_state_label)
        form.addRow("Mode", self.automation_mode_label)
        form.addRow("Recipe", self.automation_recipe_label)

        buttons = QHBoxLayout()
        self.automation_run_once_button = self._button("Run once", self.run_automation_once)
        self.automation_start_button = self._accent_button("Start", self.start_automation)
        self.automation_pause_button = self._button("Pause", self.pause_resume_automation)
        self.automation_stop_button = self._button("Stop", self.stop_automation)
        for button in (
            self.automation_run_once_button,
            self.automation_start_button,
            self.automation_pause_button,
            self.automation_stop_button,
        ):
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            buttons.addWidget(button, 1)
        form.addRow(buttons)
        return self._prepare_drawer_card(card)

    def _build_automation_mode_card(self):
        card = self._card("Automation Mode")
        form = QFormLayout(card)
        self._prepare_form(form)

        self.automation_mode_combo = QComboBox()
        self.automation_mode_combo.addItem("Periodic Image")
        self.automation_mode_combo.setToolTip("A1 periodically saves the oscilloscope screen as PNG.")

        self.automation_interval_value = QDoubleSpinBox()
        self.automation_interval_value.setRange(1.0, 604800.0)
        self.automation_interval_value.setDecimals(1)
        self.automation_interval_value.setValue(10.0)
        self.automation_interval_value.setSuffix("")
        self.automation_interval_value.valueChanged.connect(self._automation_update_recipe)

        self.automation_interval_unit = QComboBox()
        self.automation_interval_unit.addItems(["seconds", "minutes", "hours"])
        self.automation_interval_unit.currentTextChanged.connect(self._automation_update_recipe)

        interval_row = QWidget()
        interval_layout = QHBoxLayout(interval_row)
        interval_layout.setContentsMargins(0, 0, 0, 0)
        interval_layout.setSpacing(8)
        interval_layout.addWidget(self.automation_interval_value, 1)
        interval_layout.addWidget(self.automation_interval_unit, 1)

        form.addRow("Mode", self.automation_mode_combo)
        form.addRow("Every", interval_row)
        return self._prepare_drawer_card(card)

    def _build_automation_actions_card(self):
        card = self._card("Actions")
        layout = QVBoxLayout(card)
        self.automation_save_image = QCheckBox("Save PNG image")
        self.automation_save_image.setChecked(True)
        self.automation_save_image.setEnabled(False)
        layout.addWidget(self.automation_save_image)
        hint = QLabel("A1 implements PNG capture only. CSV and trigger actions are added by later backlog items.")
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return self._prepare_drawer_card(card)

    def _build_automation_run_limits_card(self):
        card = self._card("Run Limits")
        layout = QVBoxLayout(card)
        hint = QLabel("Unlimited until stopped manually. Count and duration limits are implemented in A8.")
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return self._prepare_drawer_card(card)

    def _build_automation_output_card(self):
        card = self._card("Output & Retention")
        layout = QVBoxLayout(card)
        self.automation_output_label = QLabel(
            "Uses File → Destination folder and PNG prefix/base/timestamp settings. "
            "Automation also appends a four-digit sequence and never silently overwrites."
        )
        self.automation_output_label.setWordWrap(True)
        layout.addWidget(self.automation_output_label)
        hint = QLabel("Retention is added in A9.")
        hint.setObjectName("MutedLabel")
        layout.addWidget(hint)
        return self._prepare_drawer_card(card)

    def _build_automation_reliability_card(self):
        card = self._card("Reliability")
        layout = QVBoxLayout(card)
        policy = QLabel(
            "No overlap / no backlog: when a timer tick arrives while the previous image is still being saved, "
            "that tick is counted as skipped instead of queueing another scope operation."
        )
        policy.setWordWrap(True)
        layout.addWidget(policy)
        hint = QLabel("Retry/reconnect policy is expanded in A11.")
        hint.setObjectName("MutedLabel")
        layout.addWidget(hint)
        return self._prepare_drawer_card(card)

    def _build_automation_current_run_card(self):
        card = self._card("Current Run")
        form = QFormLayout(card)
        self._prepare_form(form)
        self.automation_capture_count_label = QLabel("0")
        self.automation_skipped_count_label = QLabel("0")
        self.automation_failed_count_label = QLabel("0")
        self.automation_last_file_label = QLabel("--")
        self.automation_last_file_label.setWordWrap(True)
        form.addRow("Captured", self.automation_capture_count_label)
        form.addRow("Skipped", self.automation_skipped_count_label)
        form.addRow("Failed", self.automation_failed_count_label)
        form.addRow("Last file", self.automation_last_file_label)
        return self._prepare_drawer_card(card)

    # ------------------------------------------------------------------
    # Periodic-image behavior
    # ------------------------------------------------------------------
    def _automation_interval_seconds(self) -> float:
        value = float(self.automation_interval_value.value())
        factor = _INTERVAL_FACTORS[self.automation_interval_unit.currentText()]
        return value * factor

    def _automation_update_recipe(self, *_args) -> None:
        label = getattr(self, "automation_recipe_label", None)
        if label is None:
            return
        try:
            interval_s = self._automation_interval_seconds()
            config = PeriodicImageConfig(interval_s)
            interval_text = f"{config.interval_s:g} seconds"
        except Exception as exc:  # noqa: BLE001 - inline validation text.
            label.setText(f"Invalid configuration: {exc}")
            return
        label.setText(f"Every {interval_text}, save one PNG image using the File-page naming settings.")

    def _automation_refresh_status(self) -> None:
        controller = getattr(self, "_automation_controller", None)
        if controller is None:
            return
        state_label = getattr(self, "automation_state_label", None)
        if state_label is not None:
            state_label.setText(controller.state.value)
        stats = controller.statistics
        for name, value in (
            ("automation_capture_count_label", stats.succeeded),
            ("automation_skipped_count_label", stats.skipped),
            ("automation_failed_count_label", stats.failed),
        ):
            label = getattr(self, name, None)
            if label is not None:
                label.setText(str(value))
        last_label = getattr(self, "automation_last_file_label", None)
        if last_label is not None:
            last_label.setText(str(self._automation_last_path) if self._automation_last_path else "--")

        active = controller.state in {AutomationState.RUNNING, AutomationState.PAUSED}
        operation_active = bool(getattr(self, "_operation_active", False))
        connection_ok = bool(getattr(self, "_connection_ok", False))
        start = getattr(self, "automation_start_button", None)
        run_once = getattr(self, "automation_run_once_button", None)
        pause = getattr(self, "automation_pause_button", None)
        stop = getattr(self, "automation_stop_button", None)
        if start is not None:
            start.setEnabled(not active and not operation_active and connection_ok)
        if run_once is not None:
            run_once.setEnabled(not operation_active and connection_ok)
        if pause is not None:
            pause.setEnabled(active)
            pause.setText("Resume" if controller.state is AutomationState.PAUSED else "Pause")
        if stop is not None:
            stop.setEnabled(active)

    def _update_scope_control_enabled(self) -> None:
        super()._update_scope_control_enabled()
        self._automation_refresh_status()

    def start_automation(self) -> None:
        if not bool(getattr(self, "_connection_ok", False)):
            self._message("Automation", "Test the scope connection before starting automation.", error=True)
            return
        try:
            config = PeriodicImageConfig(self._automation_interval_seconds())
            self._ensure_control_page_built(FILE_PAGE_INDEX)
            self._automation_controller.start(config)
        except Exception as exc:  # noqa: BLE001 - show exact configuration failure.
            self._message("Automation", str(exc), error=True)
            return

        timer = self._automation_timer
        if timer is None:
            self._automation_controller.stop()
            self._message("Automation", "Automation timer is unavailable.", error=True)
            return
        timer.setInterval(max(1, int(round(config.interval_s * 1000.0))))
        timer.start()
        self._append_log(f"Automation A1 started: periodic image every {config.interval_s:g} s")
        self.statusBar().showMessage(f"Automation running: image every {config.interval_s:g} s")
        self._automation_refresh_status()

    def pause_resume_automation(self) -> None:
        timer = self._automation_timer
        if self._automation_controller.state is AutomationState.RUNNING:
            self._automation_controller.pause()
            if timer is not None:
                timer.stop()
            self._append_log("Automation paused")
        elif self._automation_controller.state is AutomationState.PAUSED:
            self._automation_controller.resume()
            config = self._automation_controller.config
            if timer is not None and config is not None:
                timer.setInterval(max(1, int(round(config.interval_s * 1000.0))))
                timer.start()
            self._append_log("Automation resumed")
        self._automation_refresh_status()

    def stop_automation(self) -> None:
        timer = self._automation_timer
        if timer is not None:
            timer.stop()
        was_active = self._automation_controller.state is not AutomationState.IDLE
        self._automation_controller.stop()
        if was_active:
            self._append_log("Automation stopped")
            self.statusBar().showMessage("Automation stopped")
        self._automation_refresh_status()

    def run_automation_once(self) -> None:
        if not bool(getattr(self, "_connection_ok", False)):
            self._message("Automation", "Test the scope connection before running automation.", error=True)
            return
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        self._automation_capture_image(force=True)

    def _automation_tick(self) -> None:
        self._automation_capture_image(force=False)

    def _automation_build_png_path(self, sequence: int) -> Path:
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        naming = FileNaming(
            prefix=self.png_prefix.text(),
            base=self.png_base.text(),
            extension="png",
            fallback="screen",
            add_timestamp=self.png_timestamp.isChecked(),
        )
        path = build_output_path(self.output_folder.text(), naming)
        return collision_safe_path(append_sequence(path, sequence))

    def _automation_capture_image(self, *, force: bool) -> None:
        token = self._automation_controller.begin_event(force=force)
        if token is None:
            self._automation_refresh_status()
            return

        try:
            path = self._automation_build_png_path(token.sequence)
            path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # noqa: BLE001 - output validation failure.
            self._automation_controller.finish_event(token, success=False, error=str(exc))
            self._append_log(f"Automation output error: {exc}")
            self._automation_refresh_status()
            return

        result = self._run_action(
            f"Automation image #{token.sequence:04d}",
            lambda scope: str(scope.save_image_path(path)),
        )
        if isinstance(result, str) and result:
            saved_path = Path(result)
            accepted = self._automation_controller.finish_event(token, success=True)
            self._automation_last_path = saved_path
            if accepted:
                self._last_image_path = saved_path
                self.statusBar().showMessage(f"Automation image saved: {saved_path.name}")
        else:
            error = str(getattr(self, "_last_action", "Capture failed"))
            self._automation_controller.finish_event(token, success=False, error=error)
        self._automation_refresh_status()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name.
        timer = self._automation_timer
        if timer is not None:
            timer.stop()
        self._automation_controller.stop()
        super().closeEvent(event)


__all__ = [
    "AUTOMATION_PAGE_INDEX",
    "CONTROL_PAGE_BUILDERS",
    "CONTROL_TAB_TITLES",
    "DISPLAY_PAGE_INDEX",
    "FILE_PAGE_INDEX",
    "LOG_PAGE_INDEX",
    "PAGE_SHORTCUTS",
    "QtScopeWindow",
]
