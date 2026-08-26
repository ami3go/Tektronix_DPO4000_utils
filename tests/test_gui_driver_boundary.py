from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADAPTERS = (
    ROOT / "dpo4000_utils" / "gui" / "api_scope_gui.py",
    ROOT / "dpo4000_utils" / "gui_qt" / "api_window.py",
)


class RawScopeAttributeVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.violations: list[int] = []

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802 - ast visitor API.
        if (
            node.attr == "scope"
            and isinstance(node.value, ast.Name)
            and node.value.id == "scope"
        ):
            self.violations.append(node.lineno)
        self.generic_visit(node)


def test_launched_gui_entrypoints_use_api_only_adapters():
    tk_entry = (ROOT / "dpo4000_utils" / "gui" / "styled_scope_gui.py").read_text(
        encoding="utf-8"
    )
    qt_entry = (ROOT / "dpo4000_utils" / "gui_qt" / "runner.py").read_text(
        encoding="utf-8"
    )

    assert "from .api_scope_gui import ScopeGui as BaseScopeGui" in tk_entry
    assert "from .api_window import QtScopeWindow" in qt_entry


def test_launched_gui_adapters_do_not_access_raw_scope_handle():
    for path in ADAPTERS:
        source = path.read_text(encoding="utf-8")
        visitor = RawScopeAttributeVisitor()
        visitor.visit(ast.parse(source, filename=str(path)))
        assert visitor.violations == [], f"raw scope.scope access in {path}: {visitor.violations}"
        assert 'getattr(scope, "scope"' not in source
        assert "getattr(scope, 'scope'" not in source


def test_launched_gui_adapters_do_not_import_raw_transfer_helpers():
    forbidden_imports = (
        "from ..hardcopy import",
        "from ..settings import apply_scope_settings_file",
        "from ..waveform import save_enabled_channels_to_single_csv",
    )
    for path in ADAPTERS:
        source = path.read_text(encoding="utf-8")
        for forbidden in forbidden_imports:
            assert forbidden not in source, f"{path} bypasses the public driver via {forbidden}"
