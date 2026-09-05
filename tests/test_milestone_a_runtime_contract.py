from __future__ import annotations

import ast
from pathlib import Path


def _method(tree: ast.AST, name: str) -> ast.FunctionDef:
    return next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == name
    )


def test_runner_launches_milestone_a_runtime_shell() -> None:
    runner = Path("dpo4000_utils/gui_qt/runner.py").read_text(encoding="utf-8")
    assert "from .milestone_a_window import QtScopeWindow" in runner


def test_milestone_a_gateway_is_async_and_preserves_cross_cutting_hooks() -> None:
    path = Path("dpo4000_utils/gui_qt/milestone_a_window.py")
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    method = _method(tree, "_run_action")

    keyword_only = {argument.arg for argument in method.args.kwonlyargs}
    assert {"on_success", "on_error", "retain_session"} <= keyword_only
    assert "AutomationReportQtScopeWindow._run_action" in source
    assert "_logger_health.note_capture" in source
    assert "_register_completed_artifacts" in source
    assert "_check_run_limits" in source
    assert "QEventLoop" not in source


def test_milestone_a_logger_uses_bounded_writer_after_async_capture() -> None:
    path = Path("dpo4000_utils/gui_qt/milestone_a_window.py")
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    method = _method(tree, "_logger_tick")
    segment = ast.get_source_segment(source, method) or ""

    assert "_logger_writer" in segment
    assert "writer.has_capacity()" in segment
    assert "writer.try_enqueue(result)" in segment
    assert "_logger_output_session" not in segment
    assert "on_success=captured" in segment
    assert "on_error=fail_runtime" in segment
    assert "retain_session=True" in segment


def test_writer_shutdown_has_no_nested_qt_event_loop() -> None:
    path = Path("dpo4000_utils/gui_qt/milestone_a_window.py")
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    method = _method(tree, "_wait_for_writer_stop")
    segment = ast.get_source_segment(source, method) or ""

    assert "writer.wait" in segment
    assert "QEventLoop" not in segment


def test_trigger_and_burst_overrides_restore_retention_and_limit_guards() -> None:
    source = Path("dpo4000_utils/gui_qt/milestone_a_window.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    for name in ("_trigger_cycle", "_trigger_bundle_cycle", "_automation_burst_event"):
        segment = ast.get_source_segment(source, _method(tree, name)) or ""
        assert "_check_run_limits" in segment
        assert "_retention_pre_event_guard" in segment
