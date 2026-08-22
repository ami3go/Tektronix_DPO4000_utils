from __future__ import annotations

from pathlib import Path


def test_qt_runner_uses_display_window():
    runner = Path("dpo4000_utils/gui_qt/runner.py").read_text(encoding="utf-8")
    package_init = Path("dpo4000_utils/gui_qt/__init__.py").read_text(encoding="utf-8")

    assert "from .display_window import QtScopeWindow" in runner
    assert "from .display_window import QtScopeWindow" in package_init
    assert "from .main_window import QtScopeWindow" not in runner
    assert "from .ui_practice_window import QtScopeWindow" not in runner
    assert "from .acquisition_window import QtScopeWindow" not in runner


def test_qt_stable_window_keeps_launch_contracts():
    content = Path("dpo4000_utils/gui_qt/stable_window.py").read_text(encoding="utf-8")

    assert "class QtScopeWindow(MatureQtScopeWindow)" in content
    assert "def _run_action" in content
    assert "start_scope_worker" in content
    assert "QEventLoop" in content
    assert "_run_snapshot_scope_session" in content
    assert "WINDOW_TITLE" in content
    assert "CONTROL_PAGE_BUILDERS" in content


def test_qt_display_window_adds_scope_display_controls_to_settings_page():
    content = Path("dpo4000_utils/gui_qt/display_window.py").read_text(encoding="utf-8")

    assert "class QtScopeWindow(StableQtScopeWindow)" in content
    assert "DISPLAY_PERSISTENCE_VALUES" in content
    assert "DISPLAY_SETUP_QUERIES" in content
    assert "DISPLAY_SCOPE_ACTIONS" in content
    assert "def _build_settings_tab" in content
    assert "def _build_display_settings_card" in content
    assert "Display, persistence, and screen text" in content
    assert "Contrast / backlight %" in content
    assert "Waveform intensity" in content
    assert "Graticule intensity" in content
    assert "Persistence" in content
    assert "Screen text" in content
    assert "Show text box on scope screen" in content


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
