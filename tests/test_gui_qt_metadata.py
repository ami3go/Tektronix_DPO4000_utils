from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 support.
    import tomli as tomllib


def test_pyproject_exposes_pyside6_dependency_and_single_desktop_script():
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    optional = data["project"]["optional-dependencies"]
    assert "pyside6" in optional
    assert any(dep.startswith("PySide6") for dep in optional["pyside6"])
    assert data["project"]["scripts"] == {
        "dpo4000-desk": "dpo4000_utils.gui_qt.runner:main"
    }


def test_pyside6_requirements_file_installs_package_extra():
    content = Path("requirements-pyside6.txt").read_text(encoding="utf-8")

    assert "-e .[pyside6]" in content


def test_qt_theme_keeps_text_and_choice_backgrounds_readable():
    content = Path("dpo4000_utils/gui_qt/theme.qss").read_text(encoding="utf-8")

    assert "QLabel {\n    background: transparent;" in content
    assert "QLabel#MutedLabel {\n    background: transparent;" in content
    assert "QRadioButton, QCheckBox {\n    background: transparent;" in content
    assert "QLineEdit, QComboBox, QTextEdit" in content
    assert "QGroupBox::title" in content


def test_qt_theme_styles_current_right_control_panel_and_status_strip():
    content = Path("dpo4000_utils/gui_qt/theme.qss").read_text(encoding="utf-8")

    assert "QWidget#RightControlPanel" in content
    assert "QStackedWidget#RightControlStack" in content
    assert "QWidget#ScopeStatusStrip" in content
    assert "QLabel#StatusBadgeOk" in content
    assert "QSplitter#MainSplitter::handle" in content


def test_qt_main_window_keeps_resizable_splitter_and_control_stack():
    content = Path("dpo4000_utils/gui_qt/main_window.py").read_text(encoding="utf-8")

    assert "QSplitter" in content
    assert "QStackedWidget" in content
    assert "DEFAULT_DRAWER_WIDTH" in content
    assert "_build_control_drawer" in content


def test_qt_runner_has_clear_missing_dependency_message_without_starting_event_loop():
    content = Path("dpo4000_utils/gui_qt/runner.py").read_text(encoding="utf-8")

    assert "except ModuleNotFoundError as exc:" in content
    assert "PySide6 is not installed" in content
    assert "python -m pip install -e .[pyside6]" in content
    assert "requirements-pyside6.txt" in content
    assert "raise SystemExit(" in content
