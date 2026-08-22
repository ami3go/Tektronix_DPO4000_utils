from __future__ import annotations

from pathlib import Path


def test_qt_runner_uses_titlebar_tabs_window():
    runner = Path("dpo4000_utils/gui_qt/runner.py").read_text(encoding="utf-8")
    package_init = Path("dpo4000_utils/gui_qt/__init__.py").read_text(encoding="utf-8")

    assert "from .titlebar_tabs_window import QtScopeWindow" in runner
    assert "from .titlebar_tabs_window import QtScopeWindow" in package_init
    assert "from .preview_window import QtScopeWindow" not in runner
    assert "from .measurement_window import QtScopeWindow" not in runner
    assert "from .display_window import QtScopeWindow" not in runner
    assert "from .main_window import QtScopeWindow" not in runner
    assert "from .ui_practice_window import QtScopeWindow" not in runner
    assert "from .acquisition_window import QtScopeWindow" not in runner


def test_qt_titlebar_tabs_window_uses_frameless_custom_titlebar():
    content = Path("dpo4000_utils/gui_qt/titlebar_tabs_window.py").read_text(encoding="utf-8")

    assert "class QtScopeWindow(PreviewQtScopeWindow)" in content
    assert "TITLEBAR_WINDOW_TITLE" in content
    assert "TITLEBAR_TABS_QSS" in content
    assert "Qt.WindowType.FramelessWindowHint" in content
    assert "TitlebarTabsBar" in content
    assert "TitlebarWindowTitle" in content
    assert "TitlebarTabButton" in content
    assert "TitlebarWindowButton" in content
    assert "TitlebarCloseButton" in content
    assert "def _build_titlebar_tabs_bar" in content
    assert "for index, title_text in enumerate(CONTROL_TAB_TITLES)" in content
    assert "self.application_menu_buttons.addButton(button, index)" in content
    assert "self._install_titlebar_drag_handlers" in content
    assert "def _toggle_maximized" in content
    assert "self.statusBar().setSizeGripEnabled(True)" in content


def test_qt_titlebar_tabs_buttons_are_drag_surfaces_without_stealing_clicks():
    content = Path("dpo4000_utils/gui_qt/titlebar_tabs_window.py").read_text(encoding="utf-8")

    assert "TITLEBAR_DRAG_SURFACE_PROPERTY" in content
    assert "TITLEBAR_DOUBLE_CLICK_SURFACE_PROPERTY" in content
    assert "widget.installEventFilter(self)" in content
    assert "def eventFilter" in content
    assert "QApplication.startDragDistance()" in content
    assert "self._install_titlebar_drag_handlers(button, allow_double_click=False)" in content
    assert "simple clicks pass through" in content
    assert "return False" in content
    assert "return consumed" in content
    assert "def _start_titlebar_window_move" in content
    assert "startSystemMove" in content
    assert "self.move(self._event_global_position(event) - self._titlebar_drag_position)" in content
    assert "def _reset_titlebar_drag_state" in content


def test_qt_preview_window_removes_reserved_title_band():
    content = Path("dpo4000_utils/gui_qt/preview_window.py").read_text(encoding="utf-8")

    assert "class QtScopeWindow(MeasurementQtScopeWindow)" in content
    assert "UNTITLED_PREVIEW_CARD_QSS" in content
    assert "UntitledPreviewCard" in content
    assert "card.setTitle(\"\")" in content
    assert "card.setContentsMargins(0, 0, 0, 0)" in content
    assert "card.setStyleSheet(UNTITLED_PREVIEW_CARD_QSS)" in content
    assert "layout.setContentsMargins(10, 8, 10, 10)" in content
    assert "QGroupBox#UntitledPreviewCard::title" in content
    assert "height: 0px;" in content
    assert "margin-top: 0px;" in content


def test_qt_stable_window_keeps_launch_contracts():
    content = Path("dpo4000_utils/gui_qt/stable_window.py").read_text(encoding="utf-8")

    assert "class QtScopeWindow(MatureQtScopeWindow)" in content
    assert "def _run_action" in content
    assert "start_scope_worker" in content
    assert "QEventLoop" in content
    assert "_run_snapshot_scope_session" in content
    assert "WINDOW_TITLE" in content
    assert "CONTROL_PAGE_BUILDERS" in content


def test_qt_display_window_splits_file_and_display_pages():
    content = Path("dpo4000_utils/gui_qt/display_window.py").read_text(encoding="utf-8")

    assert "class QtScopeWindow(StableQtScopeWindow)" in content
    assert "CONTROL_TAB_TITLES" in content
    assert '"File"' in content
    assert '"Display"' in content
    assert "FILE_PAGE_INDEX = 5" in content
    assert "DISPLAY_PAGE_INDEX = 6" in content
    assert "LOG_PAGE_INDEX = 7" in content
    assert "DISPLAY_PAGE_SHORTCUTS" in content
    assert '"Ctrl+7", 6, "Display"' in content
    assert '"Ctrl+8", 7, "Log"' in content
    assert "def _build_file_tab" in content
    assert "return super()._build_settings_tab()" in content
    assert "def _build_display_tab" in content
    assert "DisplayScrollArea" in content
    assert "DisplayScrollBody" in content


def test_qt_display_window_adds_scope_display_controls_to_display_page():
    content = Path("dpo4000_utils/gui_qt/display_window.py").read_text(encoding="utf-8")

    assert "DISPLAY_PERSISTENCE_VALUES" in content
    assert "DISPLAY_SETUP_QUERIES" in content
    assert "DISPLAY_SCOPE_ACTIONS" in content
    assert "def _build_display_settings_card" in content
    assert "Display, persistence, and screen text" in content
    assert "Contrast / backlight %" in content
    assert "Waveform intensity" in content
    assert "Graticule intensity" in content
    assert "Persistence" in content
    assert "Screen text" in content
    assert "Show text box on scope screen" in content
    assert "def _build_settings_tab" not in content


def test_qt_display_controls_use_dpo4000_display_and_message_scpi():
    content = Path("dpo4000_utils/gui_qt/display_window.py").read_text(encoding="utf-8")

    assert "DISPLAY:INTENSITY:BACKLIGHT?" in content
    assert "DISPLAY:INTENSITY:WAVEFORM?" in content
    assert "DISPLAY:INTENSITY:GRATICULE?" in content
    assert "DISPLAY:PERSISTENCE?" in content
    assert "MESSAGE:SHOW?" in content
    assert "MESSAGE:STATE?" in content
    assert "DISPLAY:INTENSITY:BACKLIGHT" in content
    assert "DISPLAY:INTENSITY:WAVEFORM" in content
    assert "DISPLAY:INTENSITY:GRATICULE" in content
    assert "DISPLAY:PERSISTENCE" in content
    assert "MESSAGE:SHOW" in content
    assert "MESSAGE:STATE" in content
    assert "MESSAGE:CLEAR" in content
    assert "_quote_scpi_string" in content
    assert "read_display_settings" in content
    assert "apply_display_settings" in content
    assert "clear_display_message" in content


def test_qt_display_actions_are_idn_gated():
    content = Path("dpo4000_utils/gui_qt/display_window.py").read_text(encoding="utf-8")

    assert "def _callback_requires_scope" in content
    assert "DISPLAY_SCOPE_ACTIONS" in content
    assert "return True" in content
    assert "super()._callback_requires_scope(callback)" in content


def test_qt_measurement_window_adds_existing_measurement_manager():
    content = Path("dpo4000_utils/gui_qt/measurement_window.py").read_text(encoding="utf-8")

    assert "class QtScopeWindow(DisplayQtScopeWindow)" in content
    assert "MEASUREMENT_MANAGEMENT_ACTIONS" in content
    assert "MEASUREMENT_SETUP_QUERIES" in content
    assert "MEASUREMENT_TABLE_HEADERS" in content
    assert "Existing scope measurements" in content
    assert "ExistingMeasurementsTable" in content
    assert "Read configured" in content
    assert "Load selected" in content
    assert "Apply edit" in content
    assert "Read value" in content
    assert "Delete selected" in content
    assert "def read_existing_measurements" in content
    assert "def load_selected_measurement_for_edit" in content
    assert "def apply_selected_measurement_edit" in content
    assert "def delete_selected_measurement" in content
    assert "def read_selected_measurement_value" in content


def test_qt_measurement_manager_uses_large_action_button_grid():
    content = Path("dpo4000_utils/gui_qt/measurement_window.py").read_text(encoding="utf-8")

    assert "QGridLayout" in content
    assert "QSizePolicy" in content
    assert "MEASUREMENT_MANAGER_BUTTON_MIN_HEIGHT = 38" in content
    assert "MEASUREMENT_MANAGER_BUTTON_MIN_WIDTH = 150" in content
    assert "def _build_existing_measurements_actions" in content
    assert "MeasurementManagerActions" in content
    assert "grid.setHorizontalSpacing(8)" in content
    assert "grid.setVerticalSpacing(8)" in content
    assert "button.setMinimumHeight(MEASUREMENT_MANAGER_BUTTON_MIN_HEIGHT)" in content
    assert "button.setMinimumWidth(MEASUREMENT_MANAGER_BUTTON_MIN_WIDTH)" in content
    assert "button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)" in content
    assert "grid.addWidget(button, row, column, row_span, column_span)" in content


def test_qt_measurement_manager_reads_and_edits_meas_scpi_slots():
    content = Path("dpo4000_utils/gui_qt/measurement_window.py").read_text(encoding="utf-8")

    assert "MEASUREMENT:MEAS{slot}:STATE?" in content
    assert "MEASUREMENT:MEAS{slot}:TYPE?" in content
    assert "MEASUREMENT:MEAS{slot}:SOURCE1?" in content
    assert "MEASUREMENT:MEAS{slot}:SOURCE2?" in content
    assert "MEASUREMENT:MEAS{slot}:VALUE?" in content
    assert "scope.add_measurement(config)" in content
    assert "scope.disable_measurement(slot)" in content
    assert "scope.read_measurement_value(slot)" in content
    assert "_set_measurement_editor" in content
    assert "_selected_measurement_config_for_slot" in content


def test_qt_measurement_management_actions_are_idn_gated():
    content = Path("dpo4000_utils/gui_qt/measurement_window.py").read_text(encoding="utf-8")

    assert "def _callback_requires_scope" in content
    assert "MEASUREMENT_MANAGEMENT_ACTIONS" in content
    assert "return True" in content
    assert "super()._callback_requires_scope(callback)" in content


def test_qt_acquisition_setup_contract_is_preserved():
    content = Path("dpo4000_utils/gui_qt/acquisition_window.py").read_text(encoding="utf-8")

    assert "ACQUISITION_MODES" in content
    assert '"HIRES"' in content
    assert '"AVERAGE"' in content
    assert "AVERAGE_COUNTS" in content
    assert "RECORD_LENGTHS" in content
    assert '"1k"' in content
    assert '"10k"' in content
    assert '"100k"' in content
    assert '"1M"' in content
    assert '"10M"' in content
    assert "ACQUIRE:MODE?" in content
    assert "ACQUIRE:NUMAVG?" in content
    assert "HORIZONTAL:RECORDLENGTH?" in content
    assert "_update_average_count_enabled" in content
    assert "use_average_count = mode == \"AVERAGE\"" in content


def test_qt_trigger_page_keeps_fast_access_controls():
    content = Path("dpo4000_utils/gui_qt/acquisition_window.py").read_text(encoding="utf-8")

    assert "def _build_trigger_acquisition_toolbar" in content
    assert "TriggerAcquisitionToolbar" in content
    assert '"Run", self.run_acquisition' in content
    assert '"Stop", self.stop_acquisition' in content
    assert '"Single", self.single_acquisition' in content
    assert '"Continuous", self.continuous_acquisition' in content
    assert '"Force", self.force_trigger' in content
    assert "Manual acquisition buttons" not in content


def test_qt_preview_toolbar_keeps_preview_and_duplicate_trigger_controls():
    content = Path("dpo4000_utils/gui_qt/acquisition_window.py").read_text(encoding="utf-8")

    quick_block = content[
        content.index("def _build_quick_control_bar"):content.index("    # ------------------------------------------------------------------\n    # Top application menu layout")
    ]
    assert '"IDN", self.test_connection' in quick_block
    assert '"Capture", self.capture_preview' in quick_block
    assert '"Copy", self.copy_preview' in quick_block
    assert '"PNG", self.save_png_image' in quick_block
    assert '"CSV", self.save_csv' in quick_block
    assert '"Run", self.run_acquisition' in quick_block
    assert '"Stop", self.stop_acquisition' in quick_block
    assert '"Single", self.single_acquisition' in quick_block
    assert '"Continuous", self.continuous_acquisition' in quick_block
    assert '"Force", self.force_trigger' in quick_block


def test_qt_channel_and_math_configuration_scpi_is_preserved():
    content = Path("dpo4000_utils/gui_qt/enhanced_window.py").read_text(encoding="utf-8")

    assert "Full channel configuration" in content
    assert "Math channel configuration" in content
    assert "read_channel_configuration" in content
    assert "apply_channel_configuration" in content
    assert "read_math_configuration" in content
    assert "apply_math_configuration" in content
    assert "CH{channel}:SCALE?" in content
    assert "CH{channel}:OFFSET?" in content
    assert "MATH:DEFINE?" in content
    assert "MATH:VERTICAL:SCALE?" in content


def test_qt_preview_has_ctrl_c_and_no_bottom_button_row():
    content = Path("dpo4000_utils/gui_qt/enhanced_window.py").read_text(encoding="utf-8")

    preview_block = content[content.index("def _build_preview_card"):content.index("    def _quick_button")]
    assert "_build_quick_control_bar" in preview_block
    assert "QKeySequence.StandardKey.Copy" in preview_block
    assert "preview_copy_shortcut" in preview_block
    assert "Save PNG image..." not in preview_block
    assert "Save enabled channels to CSV..." not in preview_block
