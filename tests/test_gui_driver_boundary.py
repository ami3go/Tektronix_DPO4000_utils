from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QT_API_ADAPTER = ROOT / "dpo4000_utils" / "gui_qt" / "api_window.py"
QT_DESKTOP_WINDOW = ROOT / "dpo4000_utils" / "gui_qt" / "desktop_window.py"
QT_BUS_WINDOW = ROOT / "dpo4000_utils" / "gui_qt" / "bus_window.py"
QT_PREVIEW_WINDOW = ROOT / "dpo4000_utils" / "gui_qt" / "preview_actions_window.py"
QT_POLISH_WINDOW = ROOT / "dpo4000_utils" / "gui_qt" / "ui_polish_window.py"
QT_AUTOMATION_WINDOW = ROOT / "dpo4000_utils" / "gui_qt" / "automation_window.py"
QT_AUTOMATION_REVIEW_WINDOW = ROOT / "dpo4000_utils" / "gui_qt" / "automation_review_window.py"
QT_TRIGGER_WINDOW = ROOT / "dpo4000_utils" / "gui_qt" / "automation_trigger_window.py"
QT_TRIGGER_REVIEW_WINDOW = ROOT / "dpo4000_utils" / "gui_qt" / "automation_trigger_review_window.py"
QT_TRIGGER_BUNDLE_WINDOW = ROOT / "dpo4000_utils" / "gui_qt" / "automation_trigger_bundle_window.py"
QT_WAVEFORM_WINDOW = ROOT / "dpo4000_utils" / "gui_qt" / "automation_waveform_window.py"
QT_MEASUREMENT_WINDOW = ROOT / "dpo4000_utils" / "gui_qt" / "automation_measurement_window.py"
QT_MEASUREMENT_REVIEW_WINDOW = ROOT / "dpo4000_utils" / "gui_qt" / "automation_measurement_review_window.py"
QT_BOUNDARY_FILES = (
    QT_API_ADAPTER,
    QT_DESKTOP_WINDOW,
    QT_BUS_WINDOW,
    QT_PREVIEW_WINDOW,
    QT_POLISH_WINDOW,
    QT_AUTOMATION_WINDOW,
    QT_AUTOMATION_REVIEW_WINDOW,
    QT_TRIGGER_WINDOW,
    QT_TRIGGER_REVIEW_WINDOW,
    QT_TRIGGER_BUNDLE_WINDOW,
    QT_WAVEFORM_WINDOW,
    QT_MEASUREMENT_WINDOW,
    QT_MEASUREMENT_REVIEW_WINDOW,
)


class RawScopeAttributeVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[int] = []

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802 - ast visitor API.
        if node.attr == "scope" and isinstance(node.value, ast.Name) and node.value.id == "scope":
            self.violations.append(node.lineno)
        self.generic_visit(node)


def test_desktop_entrypoint_uses_final_pyside_window():
    runner = (ROOT / "dpo4000_utils" / "gui_qt" / "runner.py").read_text(encoding="utf-8")
    package_init = (ROOT / "dpo4000_utils" / "gui_qt" / "__init__.py").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "from .automation_measurement_review_window import QtScopeWindow" in runner
    assert "from .automation_measurement_review_window import QtScopeWindow" in package_init
    assert 'dpo4000-desk = "dpo4000_utils.gui_qt.runner:main"' in pyproject
    assert "dpo4000-gui" not in pyproject


def test_pyside_boundary_does_not_access_raw_scope_handle():
    for path in QT_BOUNDARY_FILES:
        source = path.read_text(encoding="utf-8")
        visitor = RawScopeAttributeVisitor()
        visitor.visit(ast.parse(source, filename=str(path)))
        assert visitor.violations == [], f"raw scope.scope access in {path}: {visitor.violations}"
        assert 'getattr(scope, "scope"' not in source
        assert "getattr(scope, 'scope'" not in source


def test_pyside_boundary_does_not_import_raw_transfer_helpers():
    forbidden_imports = (
        "from ..hardcopy import",
        "from ..settings import apply_scope_settings_file",
        "from ..waveform import save_enabled_channels_to_single_csv",
    )
    for path in QT_BOUNDARY_FILES:
        source = path.read_text(encoding="utf-8")
        for forbidden in forbidden_imports:
            assert forbidden not in source


def test_bus_window_uses_public_driver_api_not_bus_scpi():
    source = QT_BUS_WINDOW.read_text(encoding="utf-8")
    assert "scope.get_bus_configuration(bus)" in source
    assert "scope.configure_bus(config)" in source
    assert "BUS:B" not in source
    assert ".query(" not in source
    assert ".write(" not in source


def test_preview_window_uses_public_driver_image_api_not_raw_scpi():
    source = QT_PREVIEW_WINDOW.read_text(encoding="utf-8")
    assert "scope.read_screen_png()" in source
    assert "scope.save_image_path(path)" in source
    assert ".query(" not in source
    assert ".write(" not in source
    assert "HARDCOPY" not in source


def test_polish_window_uses_public_driver_workflow_apis_not_raw_scpi():
    source = QT_POLISH_WINDOW.read_text(encoding="utf-8")
    assert "scope.get_record_length()" in source
    assert "scope.save_all_channels_to_single_csv(" in source
    assert "scope.restore_default_setup()" in source
    assert ".query(" not in source
    assert ".write(" not in source
    assert 'getattr(scope, "scope"' not in source


def test_automation_window_uses_public_driver_image_api_not_raw_scpi():
    source = QT_AUTOMATION_WINDOW.read_text(encoding="utf-8")
    assert "scope.save_image_path(path)" in source
    assert ".query(" not in source
    assert ".write(" not in source
    assert "HARDCOPY" not in source
    assert "CURVE?" not in source


def test_trigger_automation_uses_public_driver_methods_only():
    source = QT_TRIGGER_WINDOW.read_text(encoding="utf-8")
    for call in (
        "scope.single_acquisition()",
        "scope.get_acquisition_state()",
        "scope.get_trigger_state()",
        "scope.stop_acquisition()",
        "scope.save_image_path(path)",
    ):
        assert call in source
    assert ".query(" not in source
    assert ".write(" not in source


def test_trigger_bundle_window_delegates_scope_io_to_framework_neutral_helper():
    source = QT_TRIGGER_BUNDLE_WINDOW.read_text(encoding="utf-8")
    assert "acquire_trigger_bundle(" in source
    assert ".query(" not in source
    assert ".write(" not in source
    assert "CURVE?" not in source


def test_waveform_window_delegates_scope_io_to_framework_neutral_helper():
    source = QT_WAVEFORM_WINDOW.read_text(encoding="utf-8")
    assert "save_full_record_csv(" in source
    assert "save_image_path" not in source
    assert ".query(" not in source
    assert ".write(" not in source
    assert "CURVE?" not in source


def test_measurement_window_delegates_scope_io_to_framework_neutral_helper():
    source = QT_MEASUREMENT_WINDOW.read_text(encoding="utf-8")
    review_source = QT_MEASUREMENT_REVIEW_WINDOW.read_text(encoding="utf-8")
    assert "append_measurement_row(" in source
    assert ".query(" not in source
    assert ".write(" not in source
    assert "MEASUREMENT:" not in source
    assert ".query(" not in review_source
    assert ".write(" not in review_source


def test_connection_test_feedback_is_non_modal_and_refreshes_scope_cards():
    source = QT_DESKTOP_WINDOW.read_text(encoding="utf-8")
    assert "self._message(" not in source
    assert 'self.statusBar().showMessage(f"Connected: {idn}")' in source
    assert "self.refresh_scope_parameters()" in source
    assert "read_scope_snapshot(scope)" in source
    assert 'self.statusBar().showMessage(f"{prefix}: {error_text}")' in source
    assert 'self._last_idn = f"Error: {error_text}"' in source
    assert "return super()._finish_scope_action_error(description, exc)" in source


def test_python_package_has_no_tkinter_imports():
    violations: list[str] = []
    for path in (ROOT / "dpo4000_utils").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                if any(alias.name == "tkinter" or alias.name.startswith("tkinter.") for alias in node.names):
                    violations.append(str(path.relative_to(ROOT)))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "tkinter" or module.startswith("tkinter."):
                    violations.append(str(path.relative_to(ROOT)))
    assert violations == []
