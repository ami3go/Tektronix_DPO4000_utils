from __future__ import annotations

from pathlib import Path


def test_shared_build_helper_targets_pyside6_stable_runner_entry():
    content = Path("scripts/build_app.py").read_text(encoding="utf-8")

    assert "dpo4000_utils.gui_qt.runner import main" in content
    assert "dpo4000_utils/gui_qt/runner.py" not in content
    assert "dpo4000_utils.gui_qt.stable_window" in content
    assert "dpo4000_utils.gui_qt.scope_worker" in content
    assert "dpo4000_utils.gui_qt.startup_debug" in content
    assert "PyInstaller" in content
    assert "--collect-all" in content
    assert "PySide6" in content
    assert ".[build,pyside6]" in content


def test_shared_build_helper_has_safe_flags_and_dry_run():
    content = Path("scripts/build_app.py").read_text(encoding="utf-8")

    assert "argparse.BooleanOptionalAction" in content
    assert "--no-clean" in content
    assert "--dry-run" in content
    assert "BUILD_SKIP_INSTALL" in content
    assert "BUILD_CONSOLE" in content
    assert "def format_command" in content
    assert "shlex.quote" in content
    assert "dry_run=args.dry_run" in content
    assert "Dry run output would be" in content


def test_windows_and_linux_wrappers_call_shared_build_helper_safely():
    windows = Path("scripts/build_windows_exe.bat").read_text(encoding="utf-8")
    linux = Path("scripts/build_linux_executable.sh").read_text(encoding="utf-8")
    compat = Path("scripts/build_exe.bat").read_text(encoding="utf-8")

    assert "scripts\\build_app.py" in windows
    assert '--mode "%BUILD_MODE%"' in windows
    assert '--app-name "%APP_NAME%"' in windows
    assert "%*" in windows
    assert "python --version" in windows
    assert "TektronixDPO4000" in windows
    assert "py -3 scripts\\build_app.py" not in windows

    assert 'PYTHON_BIN="${PYTHON:-python3}"' in linux
    assert '"$PYTHON_BIN" scripts/build_app.py' in linux
    assert '--mode "$BUILD_MODE"' in linux
    assert '--app-name "$APP_NAME"' in linux
    assert '"$@"' in linux
    assert "--dry-run" in linux
    assert "TektronixDPO4000" in linux
    assert "python3 scripts/build_app.py" not in linux

    assert "build_windows_exe.bat" in compat


def test_application_build_guide_documents_platform_commands_and_outputs():
    guide = Path("docs/build-application.md").read_text(encoding="utf-8")

    assert "dpo4000-gui-qt" in guide
    assert "stable_window.QtScopeWindow" in guide
    assert "scripts\\build_windows_exe.bat" in guide
    assert "scripts/build_linux_executable.sh" in guide
    assert "python scripts/build_app.py" in guide
    assert "--dry-run" in guide
    assert "dist\\TektronixDPO4000\\TektronixDPO4000.exe" in guide
    assert "dist/TektronixDPO4000/TektronixDPO4000" in guide
    assert "BUILD_MODE=onefile" in guide
    assert "VISA runtime" in guide
