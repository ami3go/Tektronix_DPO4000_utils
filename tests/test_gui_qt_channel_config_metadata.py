from __future__ import annotations

from pathlib import Path


def test_qt_runner_uses_preview_actions_above_bus_desktop_api_chain():
    runner = Path("dpo4000_utils/gui_qt/runner.py").read_text(encoding="utf-8")
    package_init = Path("dpo4000_utils/gui_qt/__init__.py").read_text(encoding="utf-8")
    preview = Path("dpo4000_utils/gui_qt/preview_actions_window.py").read_text(encoding="utf-8")
    bus = Path("dpo4000_utils/gui_qt/bus_window.py").read_text(encoding="utf-8")
    desktop = Path("dpo4000_utils/gui_qt/desktop_window.py").read_text(encoding="utf-8")
    api = Path("dpo4000_utils/gui_qt/api_window.py").read_text(encoding="utf-8")

    assert "from .preview_actions_window import QtScopeWindow" in runner
    assert "from .preview_actions_window import QtScopeWindow" in package_init
    assert "from .bus_window import QtScopeWindow as BusQtScopeWindow" in preview
    assert "class QtScopeWindow(BusQtScopeWindow)" in preview
    assert "class QtScopeWindow(DesktopQtScopeWindow)" in bus
    assert "from .desktop_window import QtScopeWindow as DesktopQtScopeWindow" in bus
    assert "class QtScopeWindow(ApiQtScopeWindow)" in desktop
    assert "from .api_window import QtScopeWindow as ApiQtScopeWindow" in desktop
    assert "from .titlebar_tabs_window import QtScopeWindow as UiQtScopeWindow" in api
    assert "class QtScopeWindow(UiQtScopeWindow)" in api


def test_qt_titlebar_tabs_window_uses_frameless_custom_titlebar():
    content = Path("dpo4000_utils/gui_qt/titlebar_tabs_window.py").read_text(encoding="utf-8")

    assert "class QtScopeWindow(PreviewQtScopeWindow)" in content
    assert "TITLEBAR_WINDOW_TITLE" in content
    assert "Qt.WindowType.FramelessWindowHint" in content
    assert "TitlebarTabButton" in content
    assert "TitlebarCloseButton" in content
    assert "def _build_titlebar_tabs_bar" in content
    assert "def _toggle_maximized" in content
    assert "startSystemMove" in content


def test_qt_display_window_splits_file_and_display_pages():
    content = Path("dpo4000_utils/gui_qt/display_window.py").read_text(encoding="utf-8")

    assert "CONTROL_TAB_TITLES" in content
    assert '"File"' in content
    assert '"Display"' in content
    assert "CONTROL_PAGE_BUILDERS" in content
    assert "FILE_PAGE_INDEX = 5" in content
    assert "DISPLAY_PAGE_INDEX = 6" in content
    assert "def _build_file_tab" in content
    assert "def _build_display_tab" in content
    assert "DisplayScrollArea" in content


def test_qt_measurement_window_keeps_existing_measurement_manager():
    content = Path("dpo4000_utils/gui_qt/measurement_window.py").read_text(encoding="utf-8")

    assert "class QtScopeWindow(DisplayQtScopeWindow)" in content
    assert "Existing scope measurements" in content
    assert "ExistingMeasurementsTable" in content
    assert "Read configured" in content
    assert "Load selected" in content
    assert "Apply edit" in content
    assert "Delete selected" in content
    assert "def _set_measurement_editor" in content


def test_qt_acquisition_setup_contract_is_preserved():
    content = Path("dpo4000_utils/gui_qt/acquisition_window.py").read_text(encoding="utf-8")

    assert "ACQUISITION_MODES" in content
    assert '"HIRES"' in content
    assert '"AVERAGE"' in content
    assert "AVERAGE_COUNTS" in content
    assert "RECORD_LENGTHS" in content
    assert "_update_average_count_enabled" in content


def test_qt_channel_and_math_configuration_cards_are_preserved():
    content = Path("dpo4000_utils/gui_qt/enhanced_window.py").read_text(encoding="utf-8")

    assert "Full channel configuration" in content
    assert "Math channel configuration" in content
    assert "channel_config_channel.addItems([\"1\", \"2\", \"3\", \"4\"])" in content
    assert "read_channel_configuration" in content
    assert "apply_channel_configuration" in content
    assert "read_math_configuration" in content
    assert "apply_math_configuration" in content


def test_qt_preview_has_ctrl_c_and_quick_controls():
    content = Path("dpo4000_utils/gui_qt/enhanced_window.py").read_text(encoding="utf-8")

    preview_block = content[content.index("def _build_preview_card"):content.index("    def _quick_button")]
    assert "_build_quick_control_bar" in preview_block
    assert "QKeySequence.StandardKey.Copy" in preview_block
    assert "preview_copy_shortcut" in preview_block
