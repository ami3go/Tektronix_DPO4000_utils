from __future__ import annotations

from pathlib import Path


def test_qt_runner_uses_enhanced_channel_window():
    content = Path("dpo4000_utils/gui_qt/runner.py").read_text(encoding="utf-8")

    assert "from .enhanced_window import QtScopeWindow" in content
    assert "from .main_window import QtScopeWindow" not in content


def test_qt_package_exports_enhanced_window_lazily():
    content = Path("dpo4000_utils/gui_qt/__init__.py").read_text(encoding="utf-8")

    assert "from .enhanced_window import QtScopeWindow" in content


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
