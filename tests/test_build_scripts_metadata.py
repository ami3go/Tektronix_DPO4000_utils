from __future__ import annotations

from pathlib import Path


def test_project_version_is_v020_release():
    project = Path("pyproject.toml").read_text(encoding="utf-8")
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
    release_notes = Path("docs/releases/v0.2.0.md").read_text(encoding="utf-8")

    assert 'name = "dpo4000-utils"' in project
    assert 'version = "0.2.0"' in project
    assert 'dpo4000-desk = "dpo4000_utils.gui_qt.runner:main"' in project
    assert "dpo4000-gui-qt" not in project
    assert "\nqt = [" not in project
    assert "## v0.2.0 - 2026-08-22" in changelog
    assert "DPO4000 Desk" in changelog
    assert "old desktop command alias was removed" in changelog
    assert "dpo4000-desk_0.2.0_amd64.deb" in changelog
    assert "DPO4000Desk-x86_64.AppImage" in changelog
    assert "DPO4000Desk.flatpak" in changelog
    assert "# dpo4000-utils v0.2.0 / DPO4000 Desk" in release_notes
    assert "DPO4000Desk-windows.exe" in release_notes
    assert "DPO4000Desk-linux" in release_notes
    assert "dpo4000-desk_0.2.0_amd64.deb" in release_notes
    assert "DPO4000Desk-x86_64.AppImage" in release_notes
    assert "DPO4000Desk.flatpak" in release_notes
    assert "dpo4000-gui-qt" not in release_notes


def test_shared_build_helper_targets_pyside6_titlebar_tabs_runner_entry():
    content = Path("scripts/build_app.py").read_text(encoding="utf-8")

    assert "DPO4000 Desk PySide6 application" in content
    assert "dpo4000-desk" in content
    assert "DEFAULT_APP_NAME = \"DPO4000Desk\"" in content
    assert "dpo4000_utils.gui_qt.runner import main" in content
    assert "dpo4000_utils/gui_qt/runner.py" not in content
    assert "dpo4000_utils.gui_qt.titlebar_tabs_window" in content
    assert "dpo4000_utils.gui_qt.preview_window" in content
    assert "dpo4000_utils.gui_qt.measurement_window" in content
    assert "dpo4000_utils.gui_qt.display_window" in content
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


def test_shared_build_helper_validates_mode_app_name_and_output():
    content = Path("scripts/build_app.py").read_text(encoding="utf-8")

    assert "BUILD_MODES = (\"onedir\", \"onefile\")" in content
    assert "choices=BUILD_MODES" in content
    assert "UNSAFE_APP_NAME_CHARS" in content
    assert "def _validate_app_name" in content
    assert "--app-name cannot be empty" in content
    assert "--app-name cannot contain path separators or drive separators" in content
    assert "def output_path" in content
    assert "def verify_output_exists" in content
    assert "expected output was not found" in content
    assert "Expected executable path is a directory" in content
    assert "verify_output_exists(args.app_name, args.mode)" in content
    assert "if not args.dry_run:" in content


def test_windows_and_linux_wrappers_call_shared_build_helper_safely():
    windows = Path("scripts/build_windows_exe.bat").read_text(encoding="utf-8")
    linux = Path("scripts/build_linux_executable.sh").read_text(encoding="utf-8")
    compat = Path("scripts/build_exe.bat").read_text(encoding="utf-8")

    assert "scripts\\build_app.py" in windows
    assert '--mode "%BUILD_MODE%"' in windows
    assert '--app-name "%APP_NAME%"' in windows
    assert "%*" in windows
    assert "python --version" in windows
    assert 'findstr /C:"--dry-run"' in windows
    assert "Dry run completed; no executable was created." in windows
    assert "BUILD_MODE must be onedir or onefile" in windows
    assert "DPO4000Desk" in windows
    assert "TektronixDPO4000" not in windows
    assert "py -3 scripts\\build_app.py" not in windows

    assert 'PYTHON_BIN="${PYTHON:-python3}"' in linux
    assert '"$PYTHON_BIN" scripts/build_app.py' in linux
    assert '--mode "$BUILD_MODE"' in linux
    assert '--app-name "$APP_NAME"' in linux
    assert '"$@"' in linux
    assert "--dry-run" in linux
    assert "Dry run completed; no executable was created." in linux
    assert "BUILD_MODE must be onedir or onefile" in linux
    assert "DPO4000Desk" in linux
    assert "TektronixDPO4000" not in linux
    assert "python3 scripts/build_app.py" not in linux

    assert "build_windows_exe.bat" in compat


def test_linux_release_packaging_script_builds_expected_formats():
    script = Path("scripts/package_linux_release.sh").read_text(encoding="utf-8")

    assert "dpo4000-desk_${VERSION}_${DEB_ARCH}.deb" in script
    assert "DPO4000Desk-${APPIMAGE_ARCH}.AppImage" in script
    assert "DPO4000Desk.flatpak" in script
    assert "dpkg-deb --build" in script
    assert "appimagetool-${APPIMAGE_ARCH}.AppImage" in script
    assert "flatpak-builder --force-clean" in script
    assert "flatpak build-bundle" in script
    assert "io.github.ami3go.DPO4000Desk.desktop" in script
    assert "io.github.ami3go.DPO4000Desk.metainfo.xml" in script
    assert "BUILD_FLATPAK=\"${BUILD_FLATPAK:-1}\"" in script
    assert "REQUIRE_FLATPAK" in script


def test_gui_executable_workflow_builds_and_publishes_release_assets():
    workflow = Path(".github/workflows/build-gui-executables.yml").read_text(encoding="utf-8")

    assert "Build DPO4000 Desk Executables" in workflow
    assert "workflow_dispatch:" in workflow
    assert "release_tag:" in workflow
    assert "push:" in workflow
    assert "tags:" in workflow
    assert '"v*"' in workflow
    assert "permissions:" in workflow
    assert "contents: write" in workflow
    assert "APP_NAME: DPO4000Desk" in workflow
    assert "BUILD_MODE: onefile" in workflow
    assert "FLATPAK_RUNTIME_VERSION: \"24.08\"" in workflow
    assert "dist\\DPO4000Desk.exe" in workflow
    assert "DPO4000Desk-windows.exe" in workflow
    assert "Install Linux GUI and packaging dependencies" in workflow
    assert "flatpak-builder" in workflow
    assert "Install Flatpak runtime" in workflow
    assert "scripts/package_linux_release.sh" in workflow
    assert "DPO4000Desk-linux-packages" in workflow
    assert "DPO4000Desk-linux" in workflow
    assert "dpo4000-desk_*_amd64.deb" in workflow
    assert "DPO4000Desk-x86_64.AppImage" in workflow
    assert "DPO4000Desk.flatpak" in workflow
    assert "softprops/action-gh-release@v2" in workflow
    assert "name: DPO4000 Desk" in workflow
    assert "body_path: docs/releases/v0.2.0.md" in workflow
    assert "TektronixScopeGUI" not in workflow
    assert "TektronixDPO4000" not in workflow


def test_application_build_guide_documents_platform_commands_and_outputs():
    guide = Path("docs/build-application.md").read_text(encoding="utf-8")

    assert "dpo4000-desk" in guide
    assert "dpo4000-gui-qt" not in guide
    assert "titlebar_tabs_window.QtScopeWindow" not in guide
    assert "scripts\\build_windows_exe.bat" in guide
    assert "scripts/build_linux_executable.sh" in guide
    assert "scripts/package_linux_release.sh" in guide
    assert "python scripts/build_app.py" in guide
    assert "--dry-run" in guide
    assert "dist\\DPO4000Desk\\DPO4000Desk.exe" in guide
    assert "dist/DPO4000Desk/DPO4000Desk" in guide
    assert "BUILD_MODE=onefile" in guide
    assert "DPO4000Desk-windows.exe" in guide
    assert "DPO4000Desk-linux" in guide
    assert "dpo4000-desk_0.2.0_amd64.deb" in guide
    assert "DPO4000Desk-x86_64.AppImage" in guide
    assert "DPO4000Desk.flatpak" in guide
    assert "VISA runtime" in guide
    assert "TektronixDPO4000" not in guide
