from __future__ import annotations

import ast
from pathlib import Path

SOURCE_PATH = Path("dpo4000_utils/gui_qt/preview_actions_window.py")


def _method_source(name: str) -> str:
    source = SOURCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(SOURCE_PATH))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "QtScopeWindow":
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == name:
                    segment = ast.get_source_segment(source, item)
                    assert segment is not None
                    return segment
    raise AssertionError(f"Method {name!r} not found in {SOURCE_PATH}")


def test_quick_actions_use_preview_and_image_labels():
    source = SOURCE_PATH.read_text(encoding="utf-8")

    assert '("Preview", self.capture_preview, False)' in source
    assert '("Image", self.save_png_image, False)' in source
    assert '("Capture", self.capture_preview, False)' not in source
    assert '("PNG", self.save_png_image, False)' not in source


def test_preview_is_in_memory_and_does_not_build_or_save_a_user_file():
    body = _method_source("capture_preview")

    assert "scope.read_screen_png()" in body
    assert "save_image_path" not in body
    assert "_build_output_path" not in body
    assert "write_bytes" not in body
    assert "_last_image_path = None" in body


def test_image_keeps_persistent_png_save_behavior():
    save_body = _method_source("save_png_image")
    capture_body = _method_source("_capture_image_to")

    assert 'self._build_output_path("png")' in save_body
    assert "self._confirm_or_cancel_overwrite(path)" in save_body
    assert "self._capture_image_to(path" in save_body
    assert "scope.save_image_path(path)" in capture_body


def test_copy_preview_uses_full_resolution_in_memory_png():
    body = _method_source("copy_preview")

    assert '_last_preview_png' in body
    assert "QApplication.clipboard().setPixmap(pixmap)" in body


def test_preview_label_explains_transient_action():
    body = _method_source("_build_preview_card")

    assert "Select Preview to refresh the scope screen here." in body
