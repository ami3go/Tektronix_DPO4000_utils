from datetime import datetime
from pathlib import Path

from dpo4000_utils.gui.config import FileNaming, build_output_path, safe_filename_part


def test_safe_filename_part_replaces_invalid_characters():
    assert safe_filename_part('bad:name/for*windows', 'fallback') == 'bad_name_for_windows'


def test_safe_filename_part_uses_fallback_for_empty_value():
    assert safe_filename_part('', 'fallback') == 'fallback'


def test_build_output_path_with_timestamp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    naming = FileNaming(
        prefix='scope_',
        base='screen',
        extension='.png',
        fallback='scope_screen',
        add_timestamp=True,
    )
    path = build_output_path(
        'out',
        naming,
        timestamp=datetime(2026, 8, 19, 11, 59, 1),
    )
    assert path == tmp_path / 'out' / 'scope_screen_20260819_115901.png'


def test_build_output_path_without_timestamp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    naming = FileNaming(
        prefix='dpo4054_',
        base='setup',
        extension='json',
        fallback='dpo4054_setup',
        add_timestamp=False,
    )
    path = build_output_path(Path('settings'), naming)
    assert path == tmp_path / 'settings' / 'dpo4054_setup.json'
