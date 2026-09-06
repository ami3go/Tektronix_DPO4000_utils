from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSITION = ROOT / "dpo4000_utils" / "gui_qt" / "composition"


def _class(tree: ast.AST, name: str) -> ast.ClassDef:
    return next(node for node in ast.walk(tree) if isinstance(node, ast.ClassDef) and node.name == name)


def test_production_composition_window_directly_inherits_only_qmainwindow() -> None:
    path = COMPOSITION / "window.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    window = _class(tree, "QtScopeWindow")
    assert len(window.bases) == 1
    assert isinstance(window.bases[0], ast.Name)
    assert window.bases[0].id == "QMainWindow"


def test_runner_and_package_export_only_composed_production_window() -> None:
    runner = (ROOT / "dpo4000_utils" / "gui_qt" / "runner.py").read_text(encoding="utf-8")
    package_init = (ROOT / "dpo4000_utils" / "gui_qt" / "__init__.py").read_text(encoding="utf-8")
    expected = "from .composition.window import QtScopeWindow"
    assert expected in runner
    assert expected in package_init
    for forbidden in (
        "from .milestone_a_window import QtScopeWindow",
        "from .production_hardening_window import QtScopeWindow",
        "ProductionHardenedQtScopeWindow",
    ):
        assert forbidden not in runner
        assert forbidden not in package_init


def test_only_legacy_surface_adapter_may_import_historical_window_stack() -> None:
    allowed = COMPOSITION / "legacy_surface.py"
    violations: list[str] = []
    for path in COMPOSITION.glob("*.py"):
        if path == allowed:
            continue
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            module = node.module or ""
            if module.endswith("_window") or "milestone_a_window" in module:
                violations.append(f"{path.name}:{node.lineno}:{module}")
    assert violations == []

    legacy = allowed.read_text(encoding="utf-8")
    assert "milestone_a_window" in legacy
    assert "MilestoneAFeatureWindow" in legacy


def test_composition_services_have_explicit_cross_cutting_dependencies() -> None:
    source = (COMPOSITION / "services.py").read_text(encoding="utf-8")
    for controller in (
        "ScopeDispatchController",
        "FeaturePageController",
        "PageController",
        "LogController",
        "OutputPathController",
        "PreferencesController",
        "WindowChromeController",
        "LifecycleController",
    ):
        assert f"class {controller}" in source

    window = (COMPOSITION / "window.py").read_text(encoding="utf-8")
    for attribute in (
        "scope_controller",
        "page_controller",
        "log_controller",
        "output_controller",
        "preferences_controller",
        "window_chrome",
        "lifecycle_controller",
    ):
        assert f"self.{attribute}" in window


def test_composed_page_registry_owns_lazy_build_and_navigation_trigger() -> None:
    services = (COMPOSITION / "services.py").read_text(encoding="utf-8")
    window = (COMPOSITION / "window.py").read_text(encoding="utf-8")
    for title in (
        "Connection",
        "Channels",
        "Measurement",
        "Trigger",
        "Acquisition",
        "File",
        "Display",
        "Log",
    ):
        assert f'"{title}"' in services
    assert "def ensure_built" in services
    assert "def select" in services
    assert "surface._ensure_control_page_built = self.page_controller.ensure_built" in window
    assert "surface._select_drawer_page = self.page_controller.select" in window


def test_composition_layer_has_no_raw_visa_or_scpi_ownership() -> None:
    forbidden = (
        "import pyvisa",
        "from pyvisa",
        ".query(",
        ".write(",
        "scope.scope",
        "ResourceManager(",
        "HARDCOPY",
        "CURVE?",
    )
    violations: list[str] = []
    for path in COMPOSITION.glob("*.py"):
        if path.name == "legacy_surface.py":
            continue
        source = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in source:
                violations.append(f"{path.name}: {token}")
    assert violations == []


def test_composition_window_routes_mature_cross_cutting_methods_to_controllers() -> None:
    source = (COMPOSITION / "window.py").read_text(encoding="utf-8")
    for assignment in (
        "surface._append_log = self.log_controller.append",
        "surface._run_action = self.scope_controller.run_action",
        "surface._ensure_control_page_built = self.page_controller.ensure_built",
        "surface._select_drawer_page = self.page_controller.select",
        "surface._configured_output_folder = self.output_controller.configured_folder",
        "surface._build_output_path = self.output_controller.build_path",
        "surface._collect_preferences = self.preferences_controller.collect",
        "surface._apply_preferences = self.preferences_controller.apply",
        "surface._save_preferences_safely = self.preferences_controller.save",
    ):
        assert assignment in source
