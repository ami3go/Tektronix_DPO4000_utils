from __future__ import annotations

from pathlib import Path

SOURCE_PATH = Path("dpo4000_utils/gui_qt/ui_polish_window.py")


def _source() -> str:
    return SOURCE_PATH.read_text(encoding="utf-8")


def test_file_page_uses_folder_open_and_scope_settings_card():
    source = _source()

    assert 'self._button("Folder", self.pick_output_folder)' in source
    assert 'self._button("Open", self.open_output_folder)' in source
    assert 'self._card("Scope settings")' in source
    assert 'self._button("Save", self.save_settings)' in source
    assert 'self._accent_button("Restore", self.restore_settings)' in source
    assert 'self._button("Default", self.restore_default_scope_setup)' in source
    assert "Pick folder" not in source


def test_concise_button_labels_are_applied_to_requested_cards():
    source = _source()

    for old, new in (
        ("Read acquisition setup", "Read"),
        ("Apply acquisition setup", "Apply"),
        ("Read labels", "Read"),
        ("Apply labels", "Apply"),
        ("Read display", "Read"),
        ("Apply display", "Apply"),
        ("Clear text", "Clear"),
    ):
        assert f'"{old}": "{new}"' in source


def test_csv_uses_current_scope_record_length_and_non_modal_success_feedback():
    source = _source()

    assert "record_length = int(scope.get_record_length())" in source
    assert "point_count=record_length" in source
    assert 'self._last_action = f"CSV saved: {saved_path.name} ({point_count} points)"' in source
    assert 'self._message("CSV saved"' not in source


def test_scope_default_and_folder_open_use_public_platform_apis():
    source = _source()

    assert "scope.restore_default_setup()" in source
    assert "QDesktopServices.openUrl" in source
    assert ".query(" not in source
    assert ".write(" not in source
    assert 'getattr(scope, "scope"' not in source
