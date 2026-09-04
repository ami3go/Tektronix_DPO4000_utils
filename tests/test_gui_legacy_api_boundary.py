from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUI_ROOT = ROOT / "dpo4000_utils" / "gui_qt"

FORBIDDEN_TRANSPORT_METHODS = {
    "query",
    "query_ascii_values",
    "query_binary_values",
    "read_bytes",
    "read_raw",
    "read_stb",
    "write",
    "write_raw",
}
FORBIDDEN_IMPORT_ROOTS = {"pyvisa", "visa"}
RAW_HANDLE_ATTRIBUTES = {"_instrument", "_resource", "instrument", "resource", "scope"}
LEGACY_SCPI_MAP_NAMES = {
    "ACQUISITION_SETUP_QUERIES",
    "DISPLAY_SETUP_QUERIES",
    "MEASUREMENT_SETUP_QUERIES",
}


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


def _scope_like(node: ast.AST) -> bool:
    chain = _attribute_chain(node)
    return bool(chain) and chain[-1] == "scope"


def _violation(path: Path, node: ast.AST, message: str) -> str:
    relative = path.relative_to(ROOT)
    return f"{relative}:{getattr(node, 'lineno', '?')}: {message}"


def test_all_qt_gui_modules_stay_behind_public_driver_boundary() -> None:
    """Reject raw VISA/SCPI ownership from every present and future Qt GUI module."""
    violations: list[str] = []
    gui_files = _gui_files()
    assert gui_files, "Qt GUI source tree is unexpectedly empty"

    for path in gui_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.partition(".")[0] in FORBIDDEN_IMPORT_ROOTS:
                        violations.append(
                            _violation(path, node, f"imports raw transport module {alias.name!r}")
                        )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.partition(".")[0] in FORBIDDEN_IMPORT_ROOTS:
                    violations.append(
                        _violation(path, node, f"imports raw transport module {module!r}")
                    )
            elif isinstance(node, ast.Call):
                if (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr in FORBIDDEN_TRANSPORT_METHODS
                ):
                    violations.append(
                        _violation(
                            path,
                            node,
                            f"calls low-level transport method .{node.func.attr}()",
                        )
                    )
                elif (
                    isinstance(node.func, ast.Name)
                    and node.func.id == "getattr"
                    and len(node.args) >= 2
                    and _scope_like(node.args[0])
                    and isinstance(node.args[1], ast.Constant)
                    and node.args[1].value in RAW_HANDLE_ATTRIBUTES
                ):
                    violations.append(
                        _violation(path, node, "uses getattr() to reach a raw scope handle")
                    )
            elif (
                isinstance(node, ast.Attribute)
                and node.attr in RAW_HANDLE_ATTRIBUTES
                and _scope_like(node.value)
            ):
                violations.append(
                    _violation(path, node, f"reaches raw scope handle attribute .{node.attr}")
                )

    assert not violations, (
        "Qt GUI code must delegate instrument I/O through public dpo4000_utils APIs:\n"
        + "\n".join(violations)
    )


def test_qt_gui_does_not_reintroduce_legacy_scpi_query_maps() -> None:
    violations: list[str] = []

    for path in _gui_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            targets: list[ast.expr] = []
            if isinstance(node, ast.Assign):
                targets.extend(node.targets)
            elif isinstance(node, ast.AnnAssign):
                targets.append(node.target)
            else:
                continue

            for target in targets:
                if isinstance(target, ast.Name) and target.id in LEGACY_SCPI_MAP_NAMES:
                    violations.append(
                        _violation(path, target, f"reintroduces GUI-owned map {target.id}")
                    )

    assert not violations, "\n".join(violations)
