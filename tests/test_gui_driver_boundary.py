from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QT_API_ADAPTER = ROOT / "dpo4000_utils" / "gui_qt" / "api_window.py"
QT_DESKTOP_WINDOW = ROOT / "dpo4000_utils" / "gui_qt" / "desktop_window.py"
QT_BOUNDARY_FILES = (QT_API_ADAPTER, QT_DESKTOP_WINDOW)


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

    assert "from .desktop_window import QtScopeWindow" in runner
    assert "from .desktop_window import QtScopeWindow" in package_init
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


def test_connection_test_feedback_is_non_modal_and_status_only():
    source = QT_DESKTOP_WINDOW.read_text(encoding="utf-8")

    assert "self._message(" not in source
    assert 'self.statusBar().showMessage(f"Connected: {idn}")' in source
    assert 'self.statusBar().showMessage(f"Connection error: {error_text}")' in source
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
