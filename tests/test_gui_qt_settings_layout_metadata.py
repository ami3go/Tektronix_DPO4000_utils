from __future__ import annotations

from pathlib import Path


def test_qt_settings_page_uses_stacked_full_width_naming_fields():
    content = Path("dpo4000_utils/gui_qt/collapsible_window.py").read_text(encoding="utf-8")

    assert "def _build_settings_tab" in content
    assert "def _settings_naming_block" in content
    assert "def _settings_text_field_row" in content
    assert "SettingsNamingBlock" in content
    assert "SettingsNamingTitle" in content
    assert "SettingsTextFieldRow" in content
    assert "prefix.setMinimumWidth(180)" in content
    assert "base.setMinimumWidth(220)" in content
    assert "prefix.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)" in content
    assert "base.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)" in content
    assert "self.output_folder.setMinimumWidth(260)" in content
    assert "setMaximumWidth(105)" not in content


def test_qt_settings_page_keeps_existing_preference_widget_names():
    content = Path("dpo4000_utils/gui_qt/collapsible_window.py").read_text(encoding="utf-8")

    assert "self.output_folder = QLineEdit" in content
    assert "self.png_prefix" in content
    assert "self.png_base" in content
    assert "self.png_timestamp" in content
    assert "self.csv_prefix" in content
    assert "self.csv_base" in content
    assert "self.csv_timestamp" in content
    assert "self.settings_prefix" in content
    assert "self.settings_base" in content
    assert "self.settings_timestamp" in content
    assert "self.restore_wait_opc" in content
    assert "self.save_settings" in content
    assert "self.restore_settings" in content
