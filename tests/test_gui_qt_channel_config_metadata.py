from __future__ import annotations

from pathlib import Path


def test_qt_runner_uses_ui_practice_window():
    content = Path("dpo4000_utils/gui_qt/runner.py").read_text(encoding="utf-8")

    assert "from .ui_practice_window import QtScopeWindow" in content
    assert "from .main_window import QtScopeWindow" not in content


def test_qt_package_exports_ui_practice_window_lazily():
    content = Path("dpo4000_utils/gui_qt/__init__.py").read_text(encoding="utf-8")

    assert "from .ui_practice_window import QtScopeWindow" in content


def test_qt_ui_practice_window_adds_status_strip_and_recovery_buttons():
    content = Path("dpo4000_utils/gui_qt/ui_practice_window.py").read_text(encoding="utf-8")

    assert "ScopeStatusStrip" in content
    assert "connection_badge" in content
    assert "resource_status" in content
    assert "idn_status" in content
    assert "acquisition_status" in content
    assert "last_action_status" in content
    assert "Retry" in content
    assert "Refresh" in content
    assert "Disconnect" in content
    assert "retry_connection" in content
    assert "mark_disconnected" in content


def test_qt_ui_practice_window_uses_tabs_instead_of_launched_drawer():
    content = Path("dpo4000_utils/gui_qt/ui_practice_window.py").read_text(encoding="utf-8")
    theme = Path("dpo4000_utils/gui_qt/theme.qss").read_text(encoding="utf-8")

    assert "QTabWidget" in content
    assert "ControlTabs" in content
    assert "def _build_control_tabs" in content
    assert "tabs.addTab" in content
    assert "def _build_ui" in content
    assert "the remote drawer is not used" in content
    assert "Control drawer removed" in content
    assert "QTabWidget#ControlTabs" in theme
    assert "QTabWidget#ControlTabs::pane" in theme
    assert "QTabWidget#ControlTabs QTabBar::tab:selected" in theme


def test_qt_ui_practice_window_guards_scope_controls_until_idn():
    content = Path("dpo4000_utils/gui_qt/ui_practice_window.py").read_text(encoding="utf-8")

    assert "SCOPE_ACTION_CALLBACKS" in content
    assert "SAFE_UI_CALLBACKS" in content
    assert "_scope_controls" in content
    assert "_connection_ok" in content
    assert "_operation_active" in content
    assert "_register_button_if_scope_action" in content
    assert "_update_scope_control_enabled" in content
    assert "Test IDN first" in content
    assert "scopeAction" in content


def test_qt_ui_practice_window_adds_global_shortcuts():
    content = Path("dpo4000_utils/gui_qt/ui_practice_window.py").read_text(encoding="utf-8")

    assert "SHORTCUTS" in content
    assert "PAGE_SHORTCUTS" in content
    assert "F5" in content
    assert "Ctrl+S" in content
    assert "Ctrl+Shift+S" in content
    assert "F6" in content
    assert "F7" in content
    assert "F8" in content
    assert "Ctrl+L" in content
    assert "Ctrl+1" in content
    assert "_install_global_shortcuts" in content
    assert "_guarded_scope_call" in content


def test_qt_status_strip_and_guarded_controls_are_themed():
    content = Path("dpo4000_utils/gui_qt/theme.qss").read_text(encoding="utf-8")

    assert "QWidget#ScopeStatusStrip" in content
    assert "QLabel#StatusChip" in content
    assert "QLabel#StatusBadgeOk" in content
    assert "QLabel#StatusBadgeWarn" in content
    assert "QLabel#StatusBadgeBusy" in content
    assert "QToolButton#StatusActionButton" in content
    assert 'QPushButton[scopeAction="true"]:disabled' in content
    assert 'QToolButton[scopeAction="true"]:disabled' in content


def test_qt_enhanced_preview_supports_ctrl_c_copy():
    content = Path("dpo4000_utils/gui_qt/enhanced_window.py").read_text(encoding="utf-8")

    assert "QShortcut" in content
    assert "QKeySequence.StandardKey.Copy" in content
    assert "preview_copy_shortcut" in content
    assert "WidgetWithChildrenShortcut" in content
    assert "self.copy_preview" in content
    assert "Ctrl+C" in content


def test_qt_preview_has_quick_control_toolbar():
    content = Path("dpo4000_utils/gui_qt/enhanced_window.py").read_text(encoding="utf-8")

    assert "_build_quick_control_bar" in content
    assert 'toolbar.setObjectName("QuickControlBar")' in content
    assert "QuickControlButton" in content
    assert "QuickAccentButton" in content
    assert "self.test_connection" in content
    assert "self.capture_preview" in content
    assert "self.save_csv" in content
    assert "self.run_acquisition" in content
    assert "self.force_trigger" in content


def test_qt_drawer_has_compact_advanced_mode():
    content = Path("dpo4000_utils/gui_qt/enhanced_window.py").read_text(encoding="utf-8")

    assert "compact_mode" in content
    assert "compact_mode_button" in content
    assert "toggle_compact_mode" in content
    assert "_apply_compact_mode" in content
    assert "_register_advanced_widget" in content
    assert "CompactModeButton" in content


def test_qt_drawer_uses_compact_icon_navigation():
    content = Path("dpo4000_utils/gui_qt/enhanced_window.py").read_text(encoding="utf-8")

    assert "DRAWER_NAV_LABELS" in content
    assert "DRAWER_PAGE_ICON_NAMES" in content
    assert "DRAWER_NAV_ICON_SIZE" in content
    assert "button.setIcon(" in content
    assert "button.setIconSize(DRAWER_NAV_ICON_SIZE)" in content
    assert "ToolButtonTextUnderIcon" in content
    assert "setMinimumWidth(88)" in content
    assert "setMaximumWidth(108)" in content


def test_qt_drawer_icon_rail_and_compact_controls_are_themed():
    content = Path("dpo4000_utils/gui_qt/theme.qss").read_text(encoding="utf-8")

    assert "QToolButton#DrawerNavButton" in content
    assert "text-align: center" in content
    assert "padding: 7px 4px" in content
    assert "QLabel#PreviewLabel:focus" in content
    assert "QWidget#QuickControlBar" in content
    assert "QToolButton#QuickControlButton" in content
    assert "QToolButton#QuickAccentButton" in content
    assert "QToolButton#CompactModeButton" in content
    assert "QToolButton#CollapsibleHeader" in content
    assert "QGroupBox#CollapsibleContent" in content


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


def test_qt_channels_page_is_scrollable_and_advanced_sections_are_collapsible():
    content = Path("dpo4000_utils/gui_qt/enhanced_window.py").read_text(encoding="utf-8")

    assert "QScrollArea" in content
    assert 'scroll_name="ChannelsScrollArea"' in content
    assert 'body_name="ChannelsScrollBody"' in content
    assert "scroll.setWidgetResizable(True)" in content
    assert "_collapsible_section" in content
    assert "CollapsibleSection" in content
    assert "CollapsibleHeader" in content
    assert "QSizePolicy.Fixed" in content
    assert "setRowWrapPolicy(QFormLayout.WrapLongRows)" in content
    assert "setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)" in content


def test_qt_trigger_page_has_quick_card_and_collapsible_advanced_sections():
    content = Path("dpo4000_utils/gui_qt/enhanced_window.py").read_text(encoding="utf-8")

    assert "def _build_trigger_tab" in content
    assert "Trigger quick" in content
    assert "_build_trigger_quick_card" in content
    assert "_build_horizontal_position_card" in content
    assert "Horizontal position" in content
    assert "Edge trigger setup" in content
    assert "Image capture re-arm" in content
    assert 'scroll_name="TriggerScrollArea"' in content
    assert 'body_name="TriggerScrollBody"' in content
    assert "_keep_drawer_cards_natural_height" in content
    assert "findChildren(QGroupBox)" in content


def test_qt_scroll_areas_are_themed():
    content = Path("dpo4000_utils/gui_qt/theme.qss").read_text(encoding="utf-8")

    assert "QScrollArea#ChannelsScrollArea" in content
    assert "QScrollArea#TriggerScrollArea" in content
    assert "QWidget#ChannelsScrollBody" in content
    assert "QWidget#TriggerScrollBody" in content
    assert "QScrollBar:vertical" in content
    assert "QScrollBar::handle:vertical" in content


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
