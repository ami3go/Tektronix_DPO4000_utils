"""The PyInstaller build helper, exercised by calling it.

Packaging metadata assertions (version, changelog, entry point) stay as data checks
in test_packaging_metadata.py -- those really are about file contents. What used to
be asserted about build_app.py's *source* is checked here against what it produces.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def build_app():
    spec = importlib.util.spec_from_file_location(
        "dpo4000_build_app", ROOT / "scripts" / "build_app.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    try:
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def test_default_app_name_is_the_desktop_app(build_app):
    assert build_app.DEFAULT_APP_NAME == "DPO4000Desk"


def test_generated_entry_file_launches_the_console_script_target(build_app, monkeypatch, tmp_path):
    entry_file = tmp_path / "entry" / "dpo4000_qt_entry.py"
    monkeypatch.setattr(build_app, "ENTRY_DIR", entry_file.parent)
    monkeypatch.setattr(build_app, "ENTRY_FILE", entry_file)

    build_app.write_entry_file()

    content = entry_file.read_text(encoding="utf-8")
    assert "from dpo4000_utils.gui_qt.runner import main" in content
    assert "raise SystemExit(main())" in content
    # Must match the console script declared in pyproject.
    assert compile(content, str(entry_file), "exec")


def test_entry_file_is_not_written_on_a_dry_run(build_app, monkeypatch, capsys):
    # ENTRY_FILE must stay under ROOT: the dry-run message reports it relative to ROOT.
    entry_file = build_app.ROOT / "build" / "pytest_entry" / "dpo4000_qt_entry.py"
    monkeypatch.setattr(build_app, "ENTRY_DIR", entry_file.parent)
    monkeypatch.setattr(build_app, "ENTRY_FILE", entry_file)

    build_app.write_entry_file(dry_run=True)

    assert not entry_file.exists()
    assert "Would write" in capsys.readouterr().out


def _args(build_app, monkeypatch, extra=()):
    """Real parser defaults, so the test cannot invent a flag the script lacks."""
    monkeypatch.setattr(sys, "argv", ["build_app.py", *extra])
    return build_app.parse_args()


def test_pyinstaller_command_collects_the_app_and_qt_packages(build_app, monkeypatch):
    command = build_app.pyinstaller_command(_args(build_app, monkeypatch))
    joined = " ".join(command)

    assert "--collect-all" in joined
    assert "dpo4000_utils" in joined
    assert "PySide6" in joined
    assert str(build_app.ENTRY_FILE) in command


def test_pyinstaller_command_honours_the_build_mode(build_app, monkeypatch):
    onedir = build_app.pyinstaller_command(_args(build_app, monkeypatch, ["--mode", "onedir"]))
    onefile = build_app.pyinstaller_command(_args(build_app, monkeypatch, ["--mode", "onefile"]))

    assert "--onedir" in onedir
    assert "--onefile" in onefile
    assert "--onefile" not in onedir


def test_pyinstaller_command_carries_the_requested_app_name(build_app, monkeypatch):
    command = build_app.pyinstaller_command(
        _args(build_app, monkeypatch, ["--app-name", "CustomName"])
    )

    assert "CustomName" in " ".join(command)


def test_build_modes_are_the_two_pyinstaller_layouts(build_app):
    assert set(build_app.BUILD_MODES) == {"onedir", "onefile"}


def test_output_path_differs_between_modes(build_app):
    onedir = build_app.output_path("App", "onedir")
    onefile = build_app.output_path("App", "onefile")

    assert onedir != onefile
    assert "App" in str(onedir)
    assert "App" in str(onefile)


def test_unsafe_app_names_are_rejected(build_app):
    import argparse

    parser = argparse.ArgumentParser()
    for bad in ("with/slash", "with\\backslash", "with:colon"):
        with pytest.raises(SystemExit):
            build_app._validate_app_name(parser, bad)


def test_reasonable_app_name_is_accepted(build_app):
    import argparse

    build_app._validate_app_name(argparse.ArgumentParser(), "DPO4000Desk")
