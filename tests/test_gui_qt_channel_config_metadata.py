from __future__ import annotations

from pathlib import Path


def test_qt_runner_uses_enhanced_channel_window():
    content = Path("dpo4000_utils/gui_qt/runner.py").read_text(encoding="utf-8")

    assert "from .enhanced_window import QtScopeWindow" in content
    assert "from .main_window import QtScopeWindow" not in content


def test_qt_package_exports_enhanced_window_lazily():
    content = Path("dpo4000_utils/gui_qt/__init__.py").read_text(encoding="utf-8")

    assert "from .enhanced_window import QtScopeWindow" in content


def test_qt_enhanced_preview_supports_ctrl_c_copy():
    content = Path("dpo4000_utils/gui_qt/enhanced_window.py").read_text(encoding="utf-8")

    assert "QShortcut" in content
    assert "QKeySequence.StandardKey.Copy" in content
    assert "preview_copy_shortcut" in content
    assert "WidgetWithChildrenShortcut" in content
    assert "self.copy_preview" in content
    assert "Ctrl+C" in content


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


def test_qt_drawer_icon_rail_is_themed():
    content = Path("dpo4000_utils/gui_qt/theme.qss").read_text(encoding="utf-8")

    assert "QToolButton#DrawerNavButton" in content
    assert "text-align: center" in content
    assert "padding: 7px 4px" in content
    assert "QLabel#PreviewLabel:focus" in content


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


def test_qt_channels_page_is_scrollable_and_cards_keep_natural_height():
    content = Path("dpo4000_utils/gui_qt/enhanced_window.py").read_text(encoding="utf-8")

    assert "QScrollArea" in content
    assert 'scroll.setObjectName("ChannelsScrollArea")' in content
    assert 'body.setObjectName("ChannelsScrollBody")' in content
    assert "scroll.setWidgetResizable(True)" in content
    assert "QSizePolicy.Fixed" in content
    assert "setRowWrapPolicy(QFormLayout.WrapLongRows)" in content
    assert "setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)" in content


def test_qt_trigger_page_is_scrollable_and_cards_keep_natural_height():
    content = Path("dpo4000_utils/gui_qt/enhanced_window.py").read_text(encoding="utf-8")

    assert "def _build_trigger_tab" in content
    assert "super()._build_trigger_tab()" in content
    assert 'scroll_name="TriggerScrollArea"' in content
    assert 'body_name="TriggerScrollBody"' in content
    assert "_keep_drawer_cards_natural_height" in content
    assert "findChildren(QGroupBox)" in content
    assert "QSizePolicy.Fixed" in content


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
