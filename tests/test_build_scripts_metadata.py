from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 support.
    import tomli as tomllib


def test_project_version_and_desktop_metadata_are_current():
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    project_metadata = project["project"]
    version = project_metadata["version"]
    changelog_path = Path(f"CHANGELOG.d/v{version}.md")

    assert project_metadata["name"] == "dpo4000-utils"
    assert changelog_path.is_file(), f"Missing changelog fragment for package version {version}"

    scripts = project_metadata["scripts"]
    assert scripts["dpo4000-desk"] == "dpo4000_utils.gui_qt.runner:main"
    assert scripts["dpo4000-log"] == "dpo4000_utils.logger.log_cli:main"

    optional = project_metadata["optional-dependencies"]
    assert "pyside6" in optional
    assert any(dependency.startswith("PySide6") for dependency in optional["pyside6"])

    changelog_entry = changelog_path.read_text(encoding="utf-8")
    assert f"# v{version}" in changelog_entry


def test_shared_build_helper_targets_generated_desktop_entry():
    content = Path("scripts/build_app.py").read_text(encoding="utf-8")

    assert "DPO4000 Desk PySide6 application" in content
    assert "DEFAULT_APP_NAME = \"DPO4000Desk\"" in content
    assert 'content = "from dpo4000_utils.gui_qt.runner import main\\nraise SystemExit(main())\\n"' in content
    assert "str(ENTRY_FILE)" in content
    assert "--collect-all" in content
    assert "dpo4000_utils" in content
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


def test_windows_and_linux_wrappers_call_shared_build_helper():
    windows = Path("scripts/build_windows_exe.bat").read_text(encoding="utf-8")
    linux = Path("scripts/build_linux_executable.sh").read_text(encoding="utf-8")

    assert "scripts\\build_app.py" in windows
    assert '--mode "%BUILD_MODE%"' in windows
    assert '--app-name "%APP_NAME%"' in windows
    assert "%*" in windows
    assert 'PYTHON_BIN="${PYTHON:-python3}"' in linux
    assert '"$PYTHON_BIN" scripts/build_app.py' in linux
    assert '--mode "$BUILD_MODE"' in linux
    assert '--app-name "$APP_NAME"' in linux
    assert '"$@"' in linux


def test_release_workflow_builds_desktop_assets():
    workflow = Path(".github/workflows/build-gui-executables.yml").read_text(encoding="utf-8")

    assert "Build DPO4000 Desk Executables" in workflow
    assert "workflow_dispatch:" in workflow
    assert "contents: write" in workflow
    assert "APP_NAME: DPO4000Desk" in workflow
    assert "DPO4000Desk-windows.zip" in workflow
    assert "scripts/package_linux_release.sh" in workflow
    assert "softprops/action-gh-release@v2" in workflow
    assert "docs/releases/${{ needs.prepare.outputs.release_tag }}.md" in workflow


def test_application_build_guide_documents_supported_entrypoint():
    guide = Path("docs/build-application.md").read_text(encoding="utf-8")

    assert "dpo4000-desk" in guide
    assert "scripts\\build_windows_exe.bat" in guide
    assert "scripts/build_linux_executable.sh" in guide
    assert "scripts/package_linux_release.sh" in guide
    assert "python scripts/build_app.py" in guide
    assert "--dry-run" in guide
    assert "VISA runtime" in guide
