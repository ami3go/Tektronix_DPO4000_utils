from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QT_ADAPTER = ROOT / "dpo4000_utils" / "gui_qt" / "api_window.py"


class RawScopeAttributeVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[int] = []

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802 - ast visitor API.
        if node.attr == "scope" and isinstance(node.value, ast.Name) and node.value.id == "scope":
            self.violations.append(node.lineno)
        self.generic_visit(node)


def test_desktop_entrypoint_uses_pyside_api_adapter_only():
    runner = (ROOT / "dpo4000_utils" / "gui_qt" / "runner.py").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert "from .api_window import QtScopeWindow" in runner
    assert 'dpo4000-desk = "dpo4000_utils.gui_qt.runner:main"' in pyproject
    assert "dpo4000-gui" not in pyproject


def test_pyside_adapter_does_not_access_raw_scope_handle():
    source = QT_ADAPTER.read_text(encoding="utf-8")
    visitor = RawScopeAttributeVisitor()
    visitor.visit(ast.parse(source, filename=str(QT_ADAPTER)))
    assert visitor.violations == []
    assert 'getattr(scope, "scope"' not in source
    assert "getattr(scope, 'scope'" not in source


def test_pyside_adapter_does_not_import_raw_transfer_helpers():
    source = QT_ADAPTER.read_text(encoding="utf-8")
    forbidden_imports = (
        "from ..hardcopy import",
        "from ..settings import apply_scope_settings_file",
        "from ..waveform import save_enabled_channels_to_single_csv",
    )
    for forbidden in forbidden_imports:
        assert forbidden not in source


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
