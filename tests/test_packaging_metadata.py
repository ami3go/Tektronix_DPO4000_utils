"""Packaging and release metadata.

These stay as file-content checks on purpose: pyproject and the changelog *are*
data, so reading them is the behaviour. Everything that was previously asserted
about *source code* text now lives in the behavioural GUI tests instead.
"""

from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 support.
    import tomli as tomllib


def _project() -> dict:
    return tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))


def test_project_declares_the_single_desktop_entry_point():
    project = _project()["project"]

    assert project["name"] == "dpo4000-utils"
    assert project["scripts"] == {"dpo4000-desk": "dpo4000_utils.gui_qt.runner:main"}


def test_pyside6_is_an_optional_extra():
    optional = _project()["project"]["optional-dependencies"]

    assert "pyside6" in optional
    assert any(dep.startswith("PySide6") for dep in optional["pyside6"])


def test_requirements_file_installs_the_package_extra():
    content = Path("requirements-pyside6.txt").read_text(encoding="utf-8")

    assert "-e .[pyside6]" in content


def test_version_matches_its_changelog_entry():
    version = _project()["project"]["version"]
    entry = Path(f"CHANGELOG.d/v{version}.md")

    assert entry.exists(), f"no changelog fragment for version {version}"
    text = entry.read_text(encoding="utf-8")
    assert text.startswith(f"# v{version}")
    assert f"`{version}`" in text


def test_ruff_rules_are_pinned_rather_than_left_to_the_default_set():
    """Ruff's defaults change between releases; the project must not inherit them."""
    lint = _project()["tool"]["ruff"]["lint"]

    assert lint["select"], "no explicit rule selection"
    assert "F" in lint["select"]
    assert "E501" in lint["select"], "the declared line-length is not enforced"


def test_dev_extra_pins_a_ruff_range():
    dev = _project()["project"]["optional-dependencies"]["dev"]

    ruff = next(dep for dep in dev if dep.startswith("ruff"))
    assert any(marker in ruff for marker in ("==", ">=", "<")), f"ruff is unpinned: {ruff!r}"
