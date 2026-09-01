"""Structure of the launched window: composition chain, titlebar, page split.

Replaces source-text assertions like `"class QtScopeWindow(BusQtScopeWindow)" in bus`.
Those describe how the file is written; these describe what the built window is, so
they keep working if the same structure is expressed differently.
"""

from __future__ import annotations

import pytest

from tests.conftest import button_texts

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import Qt  # noqa: E402

from dpo4000_utils.gui_qt.display_window import (  # noqa: E402
    CONTROL_PAGE_BUILDERS,
    CONTROL_TAB_TITLES,
    DISPLAY_PAGE_INDEX,
    FILE_PAGE_INDEX,
)

# The launch chain, outermost first. Each layer must actually contribute to the
# built window; a layer that stops being reachable is a real regression.
EXPECTED_CHAIN = (
    "ui_polish_window",
    "preview_actions_window",
    "bus_window",
    "desktop_window",
    "api_window",
    "titlebar_tabs_window",
)


def _launched_class():
    from dpo4000_utils.gui_qt.ui_polish_window import QtScopeWindow

    return QtScopeWindow


def test_entry_points_launch_the_same_window_class():
    """runner and the package __getattr__ must not drift apart."""
    import dpo4000_utils.gui_qt as package
    from dpo4000_utils.gui_qt import runner

    assert package.QtScopeWindow is _launched_class()
    # runner imports the class inside main(); check the module it names still resolves.
    assert runner.main.__module__ == "dpo4000_utils.gui_qt.runner"


def test_launched_window_composes_the_expected_layers_in_order():
    mro_modules = [cls.__module__.rsplit(".", 1)[-1] for cls in _launched_class().__mro__]
    positions = [mro_modules.index(name) for name in EXPECTED_CHAIN]

    assert positions == sorted(positions), (
        f"launch chain order changed: {[m for m in mro_modules if m in EXPECTED_CHAIN]}"
    )


def test_window_uses_a_frameless_custom_titlebar(make_window):
    window = make_window()

    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
    # The custom titlebar supplies its own window controls.
    assert {"×", "—", "□"} <= button_texts(window)


def test_titlebar_exposes_a_tab_button_per_control_page(make_window):
    window = make_window()
    texts = button_texts(window)

    for title in CONTROL_TAB_TITLES:
        assert title in texts, f"no titlebar tab for {title!r}"


def test_control_pages_are_split_into_file_and_display(make_window):
    window = make_window()

    assert CONTROL_TAB_TITLES[FILE_PAGE_INDEX] == "File"
    assert CONTROL_TAB_TITLES[DISPLAY_PAGE_INDEX] == "Display"
    assert CONTROL_PAGE_BUILDERS[FILE_PAGE_INDEX] == "_build_file_tab"
    assert CONTROL_PAGE_BUILDERS[DISPLAY_PAGE_INDEX] == "_build_display_tab"
    assert len(CONTROL_TAB_TITLES) == len(CONTROL_PAGE_BUILDERS)

    # Both pages must actually build.
    window._select_drawer_page(FILE_PAGE_INDEX)
    assert hasattr(window, "output_folder")
    window._select_drawer_page(DISPLAY_PAGE_INDEX)
    assert window._lazy_control_pages_built[DISPLAY_PAGE_INDEX]


def test_every_control_page_builds_without_error(make_window):
    """A page that raises would otherwise only be found by clicking its tab."""
    window = make_window()

    for index, title in enumerate(CONTROL_TAB_TITLES):
        window._select_drawer_page(index)
        assert window._lazy_control_pages_built[index], f"page {title!r} did not build"


def test_maximise_toggle_is_available(make_window):
    window = make_window()
    assert callable(window._toggle_maximized)


def test_window_keeps_a_resizable_splitter_and_a_control_stack(make_window):
    from PySide6.QtWidgets import QSplitter, QStackedWidget

    window = make_window()

    splitters = window.findChildren(QSplitter)
    assert splitters, "the preview/controls split is gone"
    assert any(s.count() >= 2 for s in splitters), "splitter has nothing to resize between"
    assert window.findChildren(QStackedWidget), "control pages are not stacked"


def test_runner_explains_a_missing_pyside6_instead_of_crashing(monkeypatch):
    """The dependency error must name the install commands, not raise ImportError."""
    import builtins

    from dpo4000_utils.gui_qt import runner

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name.startswith("PySide6"):
            raise ModuleNotFoundError("No module named 'PySide6'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(SystemExit) as excinfo:
        runner.main()

    message = str(excinfo.value)
    assert "PySide6 is not installed" in message
    assert "pip install -e .[pyside6]" in message
    assert "requirements-pyside6.txt" in message


def test_theme_selectors_match_widgets_that_actually_exist(make_window):
    """A stylesheet rule naming a widget that no longer exists is dead styling."""
    from tests.conftest import REPO_ROOT

    window = make_window()
    theme = (REPO_ROOT / "dpo4000_utils/gui_qt/theme.qss").read_text(encoding="utf-8")

    for object_name in (
        "RightControlPanel",
        "RightControlStack",
        "ScopeStatusStrip",
        "MainSplitter",
    ):
        assert f"#{object_name}" in theme, f"theme no longer styles {object_name}"
        assert window.findChild(object, object_name) is not None, (
            f"theme styles #{object_name} but no widget has that name"
        )
