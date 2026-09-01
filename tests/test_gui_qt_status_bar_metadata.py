from __future__ import annotations

import ast
from pathlib import Path

WINDOW_PATH = Path("dpo4000_utils/gui_qt/ui_practice_window.py")
THEME_PATH = Path("dpo4000_utils/gui_qt/theme.qss")


def _method_source(method_name: str) -> str:
    source = WINDOW_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == method_name:
            segment = ast.get_source_segment(source, node)
            assert segment is not None
            return segment
    raise AssertionError(f"Method {method_name!r} not found in {WINDOW_PATH}")


def test_preview_status_strip_keeps_resource_and_idn_out_of_connection_cluster():
    source = _method_source("_build_status_strip")

    assert 'self.connection_badge = QLabel("● Not tested")' in source
    assert 'self.acquisition_status = QLabel("Acq: unknown")' in source
    assert 'self.last_action_status = QLabel("Last: ready")' in source
    assert "self.resource_status = QLabel" not in source
    assert "self.idn_status = QLabel" not in source


def test_bottom_status_bar_has_resource_and_idn_permanent_sections():
    source = _method_source("_configure_bottom_status_bar")

    assert 'self.resource_status = QLabel("Resource: not selected")' in source
    assert 'self.idn_status = QLabel("IDN: not tested")' in source
    assert 'label.setObjectName("BottomStatusSection")' in source
    assert "status.addPermanentWidget(self.resource_status)" in source
    assert "status.addPermanentWidget(self.idn_status)" in source
    assert source.count("status.addPermanentWidget(self._bottom_status_separator())") == 2


def test_status_updates_continue_to_refresh_bottom_resource_and_idn():
    source = _method_source("_update_status_strip")

    assert "self.resource_status.setText(self._resource_summary())" in source
    assert 'self.idn_status.setText(f"IDN:' in source
    assert "self.acquisition_status.setText" in source
    assert "self.last_action_status.setText" in source


def test_theme_styles_bottom_status_sections_and_separators():
    theme = THEME_PATH.read_text(encoding="utf-8")

    assert "QLabel#BottomStatusSection" in theme
    assert "QFrame#BottomStatusSeparator" in theme
    assert "QStatusBar::item" in theme
