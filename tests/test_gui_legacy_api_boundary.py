from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUI_ROOT = ROOT / "dpo4000_utils" / "gui_qt"

STRICT_TRANSPORT_METHODS = {
    "query",
    "query_ascii_values",
    "query_binary_values",
    "read_raw",
    "read_stb",
    "write_raw",
}
RECEIVER_SENSITIVE_METHODS = {"read_bytes", "write"}
TRANSPORT_RECEIVER_NAMES = {
    "scope",
    "instrument",
    "inst",
    "visa_resource",
    "resource",
}
FORBIDDEN_IMPORT_ROOTS = {"pyvisa", "visa"}
RAW_HANDLE_ATTRIBUTES = {"_instrument", "_resource", "instrument", "resource", "scope"}
GUI_SCPI_MAP_NAMES = {
    "ACQUISITION_SETUP_QUERIES",
    "CHANNEL_CONFIG_QUERIES",
    "DISPLAY_SETUP_QUERIES",
    "MATH_CONFIG_QUERIES",
    "MEASUREMENT_SETUP_QUERIES",
}


@dataclass(frozen=True)
class BoundaryViolation:
    path: str
    context: str
    kind: str
    line: int

    @property
    def fingerprint(self) -> tuple[str, str, str]:
        return (self.path, self.context, self.kind)

    def format(self) -> str:
        return f"{self.path}:{self.line}: {self.context}: {self.kind}"


# These are pre-existing violations that still need to be migrated behind public driver APIs.
# Keep this baseline exact: when debt is removed, remove its fingerprint here in the same change.
# That prevents an old allowance from silently permitting the violation to return later.
KNOWN_LEGACY_DEBT: Counter[tuple[str, str, str]] = Counter(
    {
        (
            "dpo4000_utils/gui_qt/enhanced_window.py",
            "QtScopeWindow._query_optional",
            "transport-call:query:instrument",
        ): 1,
        (
            "dpo4000_utils/gui_qt/enhanced_window.py",
            "QtScopeWindow._write_if_text",
            "transport-call:write:instrument",
        ): 1,
        (
            "dpo4000_utils/gui_qt/enhanced_window.py",
            "QtScopeWindow.read_channel_configuration.action",
            "raw-handle:getattr:scope.scope",
        ): 1,
        (
            "dpo4000_utils/gui_qt/enhanced_window.py",
            "QtScopeWindow.apply_channel_configuration.action",
            "raw-handle:getattr:scope.scope",
        ): 1,
        (
            "dpo4000_utils/gui_qt/enhanced_window.py",
            "QtScopeWindow.apply_channel_configuration.action",
            "transport-call:write:instrument",
        ): 2,
        (
            "dpo4000_utils/gui_qt/enhanced_window.py",
            "QtScopeWindow.read_math_configuration.action",
            "raw-handle:getattr:scope.scope",
        ): 1,
        (
            "dpo4000_utils/gui_qt/enhanced_window.py",
            "QtScopeWindow.apply_math_configuration.action",
            "raw-handle:getattr:scope.scope",
        ): 1,
        (
            "dpo4000_utils/gui_qt/enhanced_window.py",
            "QtScopeWindow.apply_math_configuration.action",
            "transport-call:write:instrument",
        ): 2,
        (
            "dpo4000_utils/gui_qt/stable_window.py",
            "QtScopeWindow._run_snapshot_scope_session",
            "raw-handle:getattr:scope.scope",
        ): 1,
        (
            "dpo4000_utils/gui_qt/ui_practice_window.py",
            "QtScopeWindow.test_connection",
            "transport-call:query:scope.scope",
        ): 1,
        (
            "dpo4000_utils/gui_qt/ui_practice_window.py",
            "QtScopeWindow.test_connection",
            "raw-handle:scope.scope",
        ): 1,
        (
            "dpo4000_utils/gui_qt/enhanced_window.py",
            "<module>",
            "gui-scpi-map:CHANNEL_CONFIG_QUERIES",
        ): 1,
        (
            "dpo4000_utils/gui_qt/enhanced_window.py",
            "<module>",
            "gui-scpi-map:MATH_CONFIG_QUERIES",
        ): 1,
    }
)


def _gui_files() -> list[Path]:
    return sorted(path for path in GUI_ROOT.rglob("*.py") if path.is_file())


def _attribute_chain(node: ast.AST) -> tuple[str, ...]:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return tuple(reversed(parts))


def _chain_text(node: ast.AST) -> str:
    chain = _attribute_chain(node)
    return ".".join(chain) if chain else "<expression>"


def _scope_like(node: ast.AST) -> bool:
    chain = _attribute_chain(node)
    return bool(chain) and chain[-1] == "scope"


def _transport_receiver(node: ast.AST) -> bool:
    chain = _attribute_chain(node)
    return any(part in TRANSPORT_RECEIVER_NAMES for part in chain)


class GuiBoundaryVisitor(ast.NodeVisitor):
    def __init__(self, path: Path) -> None:
        self.relative_path = path.relative_to(ROOT).as_posix()
        self.context_stack: list[str] = []
        self.violations: list[BoundaryViolation] = []

    @property
    def context(self) -> str:
        return ".".join(self.context_stack) if self.context_stack else "<module>"

    def _add(self, node: ast.AST, kind: str) -> None:
        self.violations.append(
            BoundaryViolation(
                path=self.relative_path,
                context=self.context,
                kind=kind,
                line=getattr(node, "lineno", 0),
            )
        )

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        self.context_stack.append(node.name)
        self.generic_visit(node)
        self.context_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self.context_stack.append(node.name)
        self.generic_visit(node)
        self.context_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self.context_stack.append(node.name)
        self.generic_visit(node)
        self.context_stack.pop()

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            if alias.name.partition(".")[0] in FORBIDDEN_IMPORT_ROOTS:
                self._add(node, f"raw-transport-import:{alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        module = node.module or ""
        if module.partition(".")[0] in FORBIDDEN_IMPORT_ROOTS:
            self._add(node, f"raw-transport-import:{module}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        if isinstance(node.func, ast.Attribute):
            method = node.func.attr
            receiver = node.func.value
            if method in STRICT_TRANSPORT_METHODS or (
                method in RECEIVER_SENSITIVE_METHODS and _transport_receiver(receiver)
            ):
                self._add(node, f"transport-call:{method}:{_chain_text(receiver)}")
        elif (
            isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and _scope_like(node.args[0])
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
            and node.args[1].value in RAW_HANDLE_ATTRIBUTES
        ):
            self._add(
                node,
                f"raw-handle:getattr:{_chain_text(node.args[0])}.{node.args[1].value}",
            )
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        if node.attr in RAW_HANDLE_ATTRIBUTES and _scope_like(node.value):
            self._add(node, f"raw-handle:{_chain_text(node)}")
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        self._check_map_targets(node, node.targets)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802
        self._check_map_targets(node, [node.target])
        self.generic_visit(node)

    def _check_map_targets(self, node: ast.AST, targets: list[ast.expr]) -> None:
        for target in targets:
            if isinstance(target, ast.Name) and target.id in GUI_SCPI_MAP_NAMES:
                self._add(node, f"gui-scpi-map:{target.id}")


def _scan_gui_boundary() -> list[BoundaryViolation]:
    violations: list[BoundaryViolation] = []
    gui_files = _gui_files()
    assert gui_files, "Qt GUI source tree is unexpectedly empty"

    for path in gui_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = GuiBoundaryVisitor(path)
        visitor.visit(tree)
        violations.extend(visitor.violations)
    return violations


def _format_counter(counter: Counter[tuple[str, str, str]]) -> str:
    if not counter:
        return "  (none)"
    lines: list[str] = []
    for fingerprint, count in sorted(counter.items()):
        path, context, kind = fingerprint
        lines.append(f"  {count}x {path}: {context}: {kind}")
    return "\n".join(lines)


def test_all_qt_gui_modules_do_not_expand_driver_boundary_debt() -> None:
    """Keep every present and future Qt GUI module behind the public driver boundary."""
    violations = _scan_gui_boundary()
    actual = Counter(violation.fingerprint for violation in violations)
    added = actual - KNOWN_LEGACY_DEBT
    removed = KNOWN_LEGACY_DEBT - actual

    assert actual == KNOWN_LEGACY_DEBT, (
        "Qt GUI driver-boundary debt changed. New debt is forbidden. If legacy debt was "
        "removed, delete its exact KNOWN_LEGACY_DEBT fingerprint in the same change so the "
        "old allowance cannot silently permit a regression later.\n"
        "Added debt:\n"
        f"{_format_counter(added)}\n"
        "Removed debt still present in baseline:\n"
        f"{_format_counter(removed)}\n"
        "Observed findings:\n"
        + "\n".join(f"  {violation.format()}" for violation in violations)
    )
