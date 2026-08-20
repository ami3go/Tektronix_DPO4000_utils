from __future__ import annotations

import sys
import tomllib
from pathlib import Path


def test_pyproject_exposes_optional_qt_dependency_and_script():
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert "qt" in data["project"]["optional-dependencies"]
    assert any(dep.startswith("PySide6") for dep in data["project"]["optional-dependencies"]["qt"])
    assert data["project"]["scripts"]["dpo4000-gui-qt"] == "dpo4000_utils.gui_qt.runner:main"


def test_qt_theme_keeps_text_widget_backgrounds_transparent():
    content = Path("dpo4000_utils/gui_qt/theme.qss").read_text(encoding="utf-8")

    assert "QLabel {\n    background: transparent;" in content
    assert "QLabel#TitleLabel {\n    background: transparent;" in content
    assert "QLabel#MutedLabel {\n    background: transparent;" in content
    assert "QRadioButton, QCheckBox {\n    background: transparent;" in content
    assert "QGroupBox::title" in content
    assert "background: transparent;" in content


def test_qt_main_window_uses_resizable_drawer_instead_of_tabs():
    content = Path("dpo4000_utils/gui_qt/main_window.py").read_text(encoding="utf-8")

    assert "QSplitter" in content
    assert "QStackedWidget" in content
    assert "QToolButton" in content
    assert "QTabWidget" not in content
    assert "DRAWER_PAGE_TITLES" in content
    assert "DEFAULT_DRAWER_WIDTH" in content
    assert "ControlDrawer" in content
    assert "DrawerNavButton" in content
    assert "hide_control_drawer" in content
    assert "show_control_drawer" in content
    assert "toggle_drawer_pin" in content


def test_qt_drawer_theme_has_vertical_navigation_styles():
    content = Path("dpo4000_utils/gui_qt/theme.qss").read_text(encoding="utf-8")

    assert "QWidget#ControlDrawer" in content
    assert "QWidget#DrawerNav" in content
    assert "QWidget#DrawerContent" in content
    assert "QToolButton#DrawerNavButton" in content
    assert "QToolButton#DrawerNavButton:checked" in content
    assert "QSplitter#MainSplitter::handle" in content
    assert "QPushButton#DrawerShowButton" in content


def test_qt_runner_has_clear_missing_dependency_message(monkeypatch):
    from dpo4000_utils.gui_qt import runner

    class BlockPySide6Finder:
        def find_spec(self, fullname, path=None, target=None):
            if fullname.startswith("PySide6"):
                raise ModuleNotFoundError("No module named 'PySide6'")
            return None

    monkeypatch.setattr(sys, "meta_path", [BlockPySide6Finder(), *sys.meta_path])

    try:
        runner.main()
    except SystemExit as exc:
        assert "pip install -e .[qt]" in str(exc)
    else:
        raise AssertionError("runner.main() should exit with a PySide6 install hint")
