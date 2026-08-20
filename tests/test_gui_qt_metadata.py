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
