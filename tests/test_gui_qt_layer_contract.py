"""Guard the failure mode that the window inheritance chain makes easy.

The launched window is built from a linear chain of QtScopeWindow subclasses. When
a layer overrides a method without calling super(), every guard, fix and invariant
the earlier version carried is silently dropped -- nothing errors, and the method
still exists.

That is not hypothetical. collapsible_window guarded capture_preview and
save_png_image with _ensure_control_page_built; preview_actions_window, nine layers
below, redefined both without super(), and Preview and Image raised AttributeError
on every fresh launch until it was noticed by hand.

These tests do not forbid replacement -- much of the chain replaces deliberately.
They require that replacing an invariant-bearing method is a decision someone makes
on purpose, and that the amount of replacement cannot quietly grow.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

GUI_DIR = pathlib.Path(__file__).resolve().parents[1] / "dpo4000_utils" / "gui_qt"

# The launch chain, base first. Mirrors the MRO of the class the runner starts.
CHAIN = (
    "main_window",
    "enhanced_window",
    "ui_practice_window",
    "acquisition_window",
    "collapsible_window",
    "stable_window",
    "display_window",
    "measurement_window",
    "preview_window",
    "titlebar_tabs_window",
    "api_window",
    "desktop_window",
    "bus_window",
    "preview_actions_window",
    "ui_polish_window",
)

# Methods that carry a guard or invariant for every later layer. Overriding one of
# these without super() drops that guard, so it must not happen. Extend this set
# whenever a method starts enforcing something on behalf of the whole chain.
INVARIANT_BEARING = frozenset(
    {
        # Build the lazily-created page before reading widgets that live on it.
        "_build_output_path",
        "_configured_output_folder",
        "_rearm_after_image_enabled",
        "_trigger_channel_or_none",
        "_ensure_control_page_built",
        # Refuse re-entry while an instrument operation is already in flight.
        "_guarded_scope_call",
        "_reject_reentrant_scope_action",
    }
)

# Wholesale replacement that is intended. Each entry is (layer, method).
# api_window exists precisely to swap raw-SCPI handlers for public driver calls,
# and several layers rebuild a card or page from scratch rather than extending it.
# This is a snapshot, not an aspiration: it should shrink, never grow.
EXPECTED_REPLACEMENTS = 62


def _class_methods(module: str) -> dict[str, bool]:
    """Map method name -> whether it calls super().<same name>()."""
    tree = ast.parse((GUI_DIR / f"{module}.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "QtScopeWindow":
            found: dict[str, bool] = {}
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    found[item.name] = any(
                        isinstance(n, ast.Attribute)
                        and isinstance(n.value, ast.Call)
                        and isinstance(n.value.func, ast.Name)
                        and n.value.func.id == "super"
                        and n.attr == item.name
                        for n in ast.walk(item)
                    )
            return found
    return {}


def _overrides_without_super() -> list[tuple[str, str, str]]:
    """Every (layer, method, layer_it_replaces) that replaces without delegating."""
    owner: dict[str, str] = {}
    replacements: list[tuple[str, str, str]] = []
    for module in CHAIN:
        for name, calls_super in _class_methods(module).items():
            if name in owner and not calls_super:
                replacements.append((module, name, owner[name]))
            owner[name] = module
    return replacements


def test_the_chain_matches_the_launched_mro():
    """If a layer is added or reordered, the lists here must be updated too."""
    from dpo4000_utils.gui_qt.ui_polish_window import QtScopeWindow

    mro_modules = [
        cls.__module__.rsplit(".", 1)[-1]
        for cls in reversed(QtScopeWindow.__mro__)
        if cls.__module__.startswith("dpo4000_utils.gui_qt")
    ]
    assert mro_modules == list(CHAIN), (
        f"the launch chain changed:\n  expected {list(CHAIN)}\n  actual   {mro_modules}"
    )


@pytest.mark.parametrize("method", sorted(INVARIANT_BEARING))
def test_invariant_bearing_methods_are_never_replaced_without_super(method):
    owner = None
    for module in CHAIN:
        methods = _class_methods(module)
        if method not in methods:
            continue
        if owner is not None and not methods[method]:
            pytest.fail(
                f"{module}.QtScopeWindow.{method} replaces {owner}'s version without "
                f"calling super(). That drops the guard {owner} installed -- the same "
                f"way Preview and Image were broken. Either call super() or move the "
                f"guard so it cannot be bypassed."
            )
        owner = module


def test_wholesale_replacement_does_not_creep_upward():
    """Pin the amount of non-delegating override so it cannot grow unnoticed."""
    replacements = _overrides_without_super()

    assert len(replacements) <= EXPECTED_REPLACEMENTS, (
        f"non-delegating overrides grew from {EXPECTED_REPLACEMENTS} to "
        f"{len(replacements)}. New ones:\n"
        + "\n".join(
            f"  {layer}.{name} replaces {replaced}.{name}"
            for layer, name, replaced in replacements[EXPECTED_REPLACEMENTS:]
        )
    )


def test_every_layer_in_the_chain_is_reachable():
    """A layer nothing inherits from is dead weight that still has to be read."""
    from dpo4000_utils.gui_qt.ui_polish_window import QtScopeWindow

    reachable = {cls.__module__.rsplit(".", 1)[-1] for cls in QtScopeWindow.__mro__}
    unreachable = [module for module in CHAIN if module not in reachable]

    assert not unreachable, f"layers no longer reached by the launched window: {unreachable}"
