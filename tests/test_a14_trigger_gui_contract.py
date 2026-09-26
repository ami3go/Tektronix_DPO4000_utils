from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
TRIGGER_PAGE = ROOT / "dpo4000_utils" / "gui_qt" / "composition" / "pages" / "trigger.py"
LEGACY_SURFACE = ROOT / "dpo4000_utils" / "gui_qt" / "composition" / "legacy_surface.py"


def test_a14_trigger_page_uses_public_driver_boundary_only() -> None:
    source = TRIGGER_PAGE.read_text(encoding="utf-8")
    assert "scope.configure_trigger(config, holdoff=holdoff)" in source
    assert "scope.get_trigger_configuration()" in source
    assert "scope.configure_sequence_trigger(config)" in source
    assert "scope.get_sequence_trigger_configuration()" in source
    assert ".query(" not in source
    assert ".write(" not in source
    assert "scope.scope" not in source
    assert 'getattr(scope, "scope"' not in source


def test_production_surface_routes_trigger_page_through_composition() -> None:
    source = LEGACY_SURFACE.read_text(encoding="utf-8")
    assert "from .pages import build_connection_page, build_trigger_page" in source
    assert "def _build_trigger_tab(self):" in source
    assert "return build_trigger_page(self)" in source


def test_unqualified_trigger_choices_are_not_exposed_by_gui_source() -> None:
    source = TRIGGER_PAGE.read_text(encoding="utf-8")
    assert '_A_TRIGGER_TYPES = ("EDGE", "PULSE", "LOGIC", "VIDEO")' in source
    assert '_PULSE_GUI_CLASSES = ("WIDTH", "RUNT", "TIMEOUT")' in source


def test_a14_trigger_widget_contract_and_enabled_relationships() -> None:
    pytest.importorskip("PySide6")
    from PySide6.QtWidgets import QApplication, QGroupBox, QPushButton

    from dpo4000_utils.gui_qt.composition.pages.trigger import build_trigger_page

    app = QApplication.instance() or QApplication([])

    class Host:
        def _card(self, title: str):
            return QGroupBox(title)

        def _button(self, title: str, callback):
            button = QPushButton(title)
            button.clicked.connect(callback)
            return button

        def _accent_button(self, title: str, callback):
            return self._button(title, callback)

        def _prepare_form(self, form):
            return form

        def _prepare_drawer_card(self, card):
            return card

        def _collapsible_section(self, _title, widget, *, expanded=True):
            return widget

    host = Host()
    page = build_trigger_page(host)
    assert page.objectName() == "A14TriggerScrollBody"
    assert [host.a14_trigger_type.itemText(i) for i in range(host.a14_trigger_type.count())] == [
        "EDGE",
        "PULSE",
        "LOGIC",
        "VIDEO",
    ]
    assert host.a14_trigger_pages.count() == 4
    assert host.a14_trigger_pages.currentIndex() == 0

    host.a14_trigger_type.setCurrentText("PULSE")
    assert host.a14_trigger_pages.currentIndex() == 1
    host.a14_pulse_class.setCurrentText("RUNT")
    assert host.a14_pulse_threshold_high.isEnabled()
    assert host.a14_pulse_threshold_low.isEnabled()
    assert not host.a14_pulse_timeout_time.isEnabled()
    host.a14_pulse_class.setCurrentText("TIMEOUT")
    assert host.a14_pulse_timeout_time.isEnabled()
    assert not host.a14_pulse_when.isEnabled()
    assert not host.a14_pulse_threshold_high.isEnabled()

    host.a14_trigger_type.setCurrentText("LOGIC")
    assert host.a14_trigger_pages.currentIndex() == 2
    host.a14_logic_class.setCurrentText("SETHOLD")
    assert host.a14_logic_setup_time.isEnabled()
    assert host.a14_logic_hold_time.isEnabled()
    assert not host.a14_logic_function.isEnabled()
    assert "NONE" not in [
        host.a14_logic_clock_source.itemText(i)
        for i in range(host.a14_logic_clock_source.count())
    ]

    host.a14_b_by.setCurrentText("EVENTS")
    assert host.a14_b_events.isEnabled()
    assert not host.a14_b_time.isEnabled()
    host.a14_b_by.setCurrentText("TIME")
    assert host.a14_b_time.isEnabled()
    assert not host.a14_b_events.isEnabled()

    page.deleteLater()
    app.processEvents()
