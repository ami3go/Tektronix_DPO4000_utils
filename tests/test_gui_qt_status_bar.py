"""Resource and IDN live in the bottom status bar, not the preview status strip."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QFrame, QLabel  # noqa: E402


def _strip_labels(window) -> list[QLabel]:
    strip = window.findChild(object, "ScopeStatusStrip")
    return strip.findChildren(QLabel) if strip is not None else []


def test_status_strip_shows_connection_acquisition_and_last_action(make_window):
    window = make_window()

    assert window.connection_badge.text()
    assert "Acq" in window.acquisition_status.text()
    assert "Last" in window.last_action_status.text()


def test_status_strip_does_not_carry_resource_or_idn(make_window):
    window = make_window()

    strip_widgets = set(_strip_labels(window))
    assert window.resource_status not in strip_widgets
    assert window.idn_status not in strip_widgets


def test_resource_and_idn_are_permanent_bottom_status_sections(make_window):
    window = make_window()
    status = window.statusBar()

    assert window.resource_status.parent() is not None
    assert window.resource_status.objectName() == "BottomStatusSection"
    assert window.idn_status.objectName() == "BottomStatusSection"

    # Permanent widgets are reparented onto the status bar itself.
    for label in (window.resource_status, window.idn_status):
        assert status.isAncestorOf(label), f"{label.text()!r} is not on the bottom status bar"


def test_bottom_status_bar_separates_its_sections(make_window):
    window = make_window()

    separators = [
        f
        for f in window.statusBar().findChildren(QFrame)
        if f.objectName() == "BottomStatusSeparator"
    ]
    assert len(separators) == 2, f"expected two section separators, found {len(separators)}"


def test_status_refresh_updates_resource_idn_acquisition_and_last_action(make_window):
    window = make_window()

    window._last_idn = "TEKTRONIX,DPO4054,C011280,CF:91.1CT FV:v2.48"
    window._acquisition_state = "Running"
    window._last_action = "Saved CSV"
    window._update_status_strip()

    assert "DPO4054" in window.idn_status.text()
    assert window.idn_status.text().startswith("IDN:")
    assert window.resource_status.text().startswith("Resource:")
    assert "Running" in window.acquisition_status.text()
    assert "Saved CSV" in window.last_action_status.text()


def test_untested_idn_is_reported_rather_than_left_blank(make_window):
    window = make_window()
    window._update_status_strip()

    assert window.idn_status.text().strip() != "IDN:"
    assert window.resource_status.text().strip() != "Resource:"


def test_theme_styles_the_status_sections_it_defines(make_window):
    """The object names the stylesheet targets must exist on real widgets."""
    window = make_window()
    theme = window.styleSheet() or ""
    if not theme:
        from tests.conftest import REPO_ROOT

        theme = (REPO_ROOT / "dpo4000_utils/gui_qt/theme.qss").read_text(encoding="utf-8")

    for selector, object_name in (
        ("QLabel#BottomStatusSection", "BottomStatusSection"),
        ("QFrame#BottomStatusSeparator", "BottomStatusSeparator"),
    ):
        assert selector in theme, f"{selector} missing from the stylesheet"
        assert window.findChild(object, object_name) is not None, (
            f"{selector} styles nothing: no widget is named {object_name}"
        )
