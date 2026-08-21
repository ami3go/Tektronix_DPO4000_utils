from __future__ import annotations

from pathlib import Path


def test_qt_runner_uses_acquisition_window():
    content = Path("dpo4000_utils/gui_qt/runner.py").read_text(encoding="utf-8")

    assert "from .acquisition_window import QtScopeWindow" in content
    assert "from .ui_practice_window import QtScopeWindow" not in content
    assert "from .main_window import QtScopeWindow" not in content


def test_qt_package_exports_acquisition_window_lazily():
    content = Path("dpo4000_utils/gui_qt/__init__.py").read_text(encoding="utf-8")

    assert "from .acquisition_window import QtScopeWindow" in content


def test_qt_acquisition_window_adds_dedicated_setup_tab():
    content = Path("dpo4000_utils/gui_qt/acquisition_window.py").read_text(encoding="utf-8")

    assert "CONTROL_TAB_TITLES" in content
    assert '"Acquisition"' in content
    assert "def _build_acquisition_tab" in content
    assert "_build_acquisition_setup_card" in content
    assert 'scroll_name="AcquisitionScrollArea"' in content
    assert 'body_name="AcquisitionScrollBody"' in content
    assert "tabs.addTab(self._build_acquisition_tab(), CONTROL_TAB_TITLES[4])" in content


def test_qt_acquisition_tab_is_setup_oriented_not_manual_buttons():
    content = Path("dpo4000_utils/gui_qt/acquisition_window.py").read_text(encoding="utf-8")

    acquisition_block = content[
        content.index("def _build_acquisition_tab"):content.index("    def _build_acquisition_setup_card")
    ]
    assert "_build_acquisition_setup_card" in acquisition_block
    assert "_build_acquisition_actions_card" not in acquisition_block
    assert "_build_image_rearm_card" not in acquisition_block
    assert "Acquisition setup" in content
    assert "ACQUISITION_MODES" in content
    assert '"HIRES"' in content
    assert '"AVERAGE"' in content
    assert "AVERAGE_COUNTS" in content
    assert "RECORD_LENGTHS" in content
    assert "ACQUIRE:MODE?" in content
    assert "ACQUIRE:NUMAVG?" in content
    assert "HORIZONTAL:RECORDLENGTH?" in content
    assert "Read acquisition setup" in content
    assert "Apply acquisition setup" in content


def test_qt_acquisition_average_count_is_conditional_on_average_mode():
    content = Path("dpo4000_utils/gui_qt/acquisition_window.py").read_text(encoding="utf-8")

    assert "_is_average_mode" in content
    assert "_update_average_count_enabled" in content
    assert "currentTextChanged.connect(self._update_average_count_enabled)" in content
    assert "self.acquisition_average_count.setEnabled(enabled)" in content
    assert "mode == \"AVERAGE\"" in content
    assert "use_average_count = mode == \"AVERAGE\"" in content
    assert "if use_average_count:" in content
    assert "ACQUIRE:NUMAVG" in content
    assert "skipped" in content


def test_qt_trigger_tab_keeps_manual_acquisition_and_rearm_sections():
    content = Path("dpo4000_utils/gui_qt/acquisition_window.py").read_text(encoding="utf-8")

    trigger_block = content[
        content.index("def _build_trigger_tab"):content.index("    def _build_trigger_level_only_card")
    ]
    assert "Trigger level" in content
    assert "_build_trigger_level_only_card" in content
    assert "Horizontal position" in trigger_block
    assert "Edge trigger setup" in trigger_block
    assert "Manual acquisition buttons" in trigger_block
    assert "_build_acquisition_actions_card" in trigger_block
    assert "Image capture re-arm" in trigger_block
    assert "_build_image_rearm_card" in trigger_block


def test_qt_acquisition_shortcuts_include_seven_tabs():
    content = Path("dpo4000_utils/gui_qt/acquisition_window.py").read_text(encoding="utf-8")

    assert "PAGE_SHORTCUTS" in content
    assert '("Ctrl+5", 4, "Acquisition")' in content
    assert '("Ctrl+6", 5, "Settings")' in content
    assert '("Ctrl+7", 6, "Log")' in content
    assert "_install_global_shortcuts" in content


def test_qt_ui_practice_window_keeps_status_strip_and_guarded_controls():
    content = Path("dpo4000_utils/gui_qt/ui_practice_window.py").read_text(encoding="utf-8")

    assert "ScopeStatusStrip" in content
    assert "connection_badge" in content
    assert "resource_status" in content
    assert "idn_status" in content
    assert "acquisition_status" in content
    assert "last_action_status" in content
    assert "SCOPE_ACTION_CALLBACKS" in content
    assert "SAFE_UI_CALLBACKS" in content
    assert "_scope_controls" in content
    assert "_update_scope_control_enabled" in content
    assert "read_acquisition_setup" in content
    assert "apply_acquisition_setup" in content
    assert "Test IDN first" in content
    assert "scopeAction" in content


def test_qt_ui_practice_window_still_uses_tabs_not_launched_drawer():
    content = Path("dpo4000_utils/gui_qt/ui_practice_window.py").read_text(encoding="utf-8")
    theme = Path("dpo4000_utils/gui_qt/theme.qss").read_text(encoding="utf-8")

    assert "QTabWidget" in content
    assert "ControlTabs" in content
    assert "def _build_control_tabs" in content
    assert "tabs.addTab" in content
    assert "the remote drawer is not used" in content
    assert "Control drawer removed" in content
    assert "QTabWidget#ControlTabs" in theme
    assert "QTabWidget#ControlTabs::pane" in theme
    assert "QTabWidget#ControlTabs QTabBar::tab:selected" in theme


def test_qt_preview_has_quick_toolbar_ctrl_c_and_no_redundant_bottom_buttons():
    content = Path("dpo4000_utils/gui_qt/enhanced_window.py").read_text(encoding="utf-8")

    preview_block = content[content.index("def _build_preview_card"):content.index("    def _quick_button")]
    assert "_build_quick_control_bar" in preview_block
    assert "QKeySequence.StandardKey.Copy" in preview_block
    assert "preview_copy_shortcut" in preview_block
    assert "WidgetWithChildrenShortcut" in preview_block
    assert "self.copy_preview" in preview_block
    assert "Ctrl+C" in preview_block
    assert "Save PNG image..." not in preview_block
    assert "Save enabled channels to CSV..." not in preview_block
    assert "Copy preview\"" not in preview_block
    assert "Capture preview\"" not in preview_block


def test_qt_enhanced_preview_quick_toolbar_contains_common_actions():
    content = Path("dpo4000_utils/gui_qt/enhanced_window.py").read_text(encoding="utf-8")

    assert "_build_quick_control_bar" in content
    assert 'toolbar.setObjectName("QuickControlBar")' in content
    assert "QuickControlButton" in content
    assert "QuickAccentButton" in content
    assert "self.test_connection" in content
    assert "self.capture_preview" in content
    assert "self.copy_preview" in content
    assert "self.save_png_image" in content
    assert "self.save_csv" in content
    assert "self.run_acquisition" in content
    assert "self.force_trigger" in content


def test_qt_channels_tab_has_full_channel_and_math_configuration():
    content = Path("dpo4000_utils/gui_qt/enhanced_window.py").read_text(encoding="utf-8")

    assert "Full channel configuration" in content
    assert "Math channel configuration" in content
    assert "CHANNEL_CONFIG_FIELDS" in content
    assert "MATH_CONFIG_FIELDS" in content
    assert "read_channel_configuration" in content
    assert "apply_channel_configuration" in content
    assert "read_math_configuration" in content
    assert "apply_math_configuration" in content


def test_qt_channel_config_contains_expected_scpi_commands():
    content = Path("dpo4000_utils/gui_qt/enhanced_window.py").read_text(encoding="utf-8")

    assert "SELECT:CH{channel}?" in content
    assert "CH{channel}:SCALE?" in content
    assert "CH{channel}:POSITION?" in content
    assert "CH{channel}:OFFSET?" in content
    assert "CH{channel}:COUPLING?" in content
    assert "CH{channel}:BANDWIDTH?" in content
    assert "CH{channel}:INVERT?" in content
    assert "CH{channel}:PROBE:GAIN?" in content
    assert "SELECT:CH{channel}" in content
    assert "CH{channel}:SCALE" in content
    assert "CH{channel}:POSITION" in content
    assert "CH{channel}:OFFSET" in content
    assert "CH{channel}:COUPLING" in content
    assert "CH{channel}:BANDWIDTH" in content
    assert "CH{channel}:INVERT" in content
    assert "CH{channel}:PROBE:GAIN" in content


def test_qt_math_config_contains_expected_scpi_commands():
    content = Path("dpo4000_utils/gui_qt/enhanced_window.py").read_text(encoding="utf-8")

    assert "SELECT:MATH?" in content
    assert "MATH:DEFINE?" in content
    assert "MATH:VERTICAL:SCALE?" in content
    assert "MATH:VERTICAL:POSITION?" in content
    assert "MATH:DEFINE" in content
    assert "MATH:VERTICAL:SCALE" in content
    assert "MATH:VERTICAL:POSITION" in content
    assert "SELECT:MATH" in content
