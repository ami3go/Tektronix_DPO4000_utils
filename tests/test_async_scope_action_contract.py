from __future__ import annotations

import ast
from pathlib import Path


PRODUCTION_ASYNC_METHODS = {
    "_automation_capture_image",
    "_trigger_cycle",
    "_save_triggered_image",
    "_trigger_bundle_cycle",
    "_automation_capture_csv",
    "_automation_capture_measurements",
    "_automation_capture_condition",
    "_automation_burst_event",
    "_logger_tick",
}


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def test_final_production_state_machines_never_assign_run_action_result() -> None:
    path = Path("dpo4000_utils/gui_qt/production_hardening_window.py")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    methods = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in PRODUCTION_ASYNC_METHODS
    }
    assert set(methods) == PRODUCTION_ASYNC_METHODS

    for name, method in methods.items():
        run_action_calls = [
            node
            for node in ast.walk(method)
            if isinstance(node, ast.Call) and _call_name(node) == "_run_action"
        ]
        assert run_action_calls, f"{name} must dispatch through the shared scope gateway"
        for call in run_action_calls:
            keyword_names = {keyword.arg for keyword in call.keywords}
            assert "on_success" in keyword_names, f"{name} must finish from on_success"
            assert "on_error" in keyword_names, f"{name} must finish from on_error"

        for node in ast.walk(method):
            if not isinstance(node, (ast.Assign, ast.AnnAssign, ast.NamedExpr)):
                continue
            value = getattr(node, "value", None)
            if isinstance(value, ast.Call) and _call_name(value) == "_run_action":
                raise AssertionError(
                    f"{name} synchronously assigns _run_action(); the v0.7 gateway returns None"
                )


def test_bus_capability_startup_checks_are_callback_based() -> None:
    for filename in ("logger_bus_window.py", "logger_mixed_window.py"):
        path = Path("dpo4000_utils/gui_qt") / filename
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        start = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "start_logger"
        )
        calls = [
            node
            for node in ast.walk(start)
            if isinstance(node, ast.Call) and _call_name(node) == "_run_action"
        ]
        assert calls
        for call in calls:
            keywords = {keyword.arg for keyword in call.keywords}
            assert {"on_success", "on_error"} <= keywords


def test_gui_worker_sources_have_no_nested_qeventloop() -> None:
    for filename in (
        "scope_worker.py",
        "stable_window.py",
        "preview_actions_window.py",
        "automation_recovery_window.py",
        "production_hardening_window.py",
    ):
        content = (Path("dpo4000_utils/gui_qt") / filename).read_text(encoding="utf-8")
        assert "QEventLoop" not in content, f"nested event-loop regression in {filename}"
