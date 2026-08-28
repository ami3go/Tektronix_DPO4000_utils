from __future__ import annotations

from pathlib import Path


def test_qt_final_bus_window_sits_above_desktop_api_and_visual_layers():
    runner = Path("dpo4000_utils/gui_qt/runner.py").read_text(encoding="utf-8")
    bus = Path("dpo4000_utils/gui_qt/bus_window.py").read_text(encoding="utf-8")
    desktop = Path("dpo4000_utils/gui_qt/desktop_window.py").read_text(encoding="utf-8")

    assert "from .bus_window import QtScopeWindow" in runner
    assert "class QtScopeWindow(DesktopQtScopeWindow)" in bus
    assert "from .desktop_window import QtScopeWindow as DesktopQtScopeWindow" in bus
    assert "class QtScopeWindow(ApiQtScopeWindow)" in desktop
    assert "refresh_scope_parameters" in desktop


def test_qt_stable_window_runs_scope_actions_on_worker_thread():
    content = Path("dpo4000_utils/gui_qt/stable_window.py").read_text(encoding="utf-8")
    worker = Path("dpo4000_utils/gui_qt/scope_worker.py").read_text(encoding="utf-8")

    assert "def _run_action" in content
    assert "start_scope_worker" in content
    assert "QEventLoop" in content
    assert "class ScopeWorker(QRunnable)" in worker
    assert "QThreadPool.globalInstance().start(worker)" in worker


def test_qt_collapsible_sections_use_lightweight_clickable_header():
    content = Path("dpo4000_utils/gui_qt/collapsible_window.py").read_text(encoding="utf-8")

    assert "class CollapsibleCard(QFrame)" in content
    assert "card header itself toggles the body" in content
    assert 'self._header.setObjectName("InlineCollapsibleHeader")' in content
    assert "mousePressEvent" in content
    assert "self._header.geometry().contains(event.pos())" in content
    assert "InlineCollapsibleCard" in content
    assert "InlineCollapsibleContent" in content
    assert "parent: QWidget | None = None" in content
    assert "super().__init__(parent)" in content


def test_qt_lightweight_collapsible_card_styles_are_local():
    content = Path("dpo4000_utils/gui_qt/collapsible_window.py").read_text(encoding="utf-8")

    assert "QFrame#InlineCollapsibleCard," in content
    assert "QFrame#InlineCollapsibleCardCollapsed" in content
    assert "QLabel#InlineCollapsibleHeader" in content
    assert "QWidget#InlineCollapsibleBody" in content
    assert "QGroupBox#InlineCollapsibleContent" in content


def test_qt_control_pages_are_lazy_built():
    content = Path("dpo4000_utils/gui_qt/collapsible_window.py").read_text(encoding="utf-8")
    display = Path("dpo4000_utils/gui_qt/display_window.py").read_text(encoding="utf-8")

    assert "LazyControlPagePlaceholder" in content
    assert "def _ensure_control_page_built" in content
    assert "stack.removeWidget(placeholder)" in content
    assert "placeholder.deleteLater()" in content
    assert "self._lazy_control_pages_built[index] = True" in content
    assert "CONTROL_PAGE_BUILDERS" in display
    assert '"_build_display_tab"' in display


def test_qt_lazy_pages_apply_preferences_once_per_page():
    content = Path("dpo4000_utils/gui_qt/collapsible_window.py").read_text(encoding="utf-8")

    assert "self._pending_preferences = None" in content
    assert "self._lazy_control_pages_preferences_applied" in content
    assert "def _apply_preferences_to_control_page" in content
    assert "without overwriting live edits" in content
    assert "self._lazy_control_pages_preferences_applied[index] = True" in content


def test_qt_every_direct_card_becomes_collapsible_with_primary_open():
    content = Path("dpo4000_utils/gui_qt/collapsible_window.py").read_text(encoding="utf-8")

    assert "def _make_page_cards_collapsible" in content
    assert "expanded=plain_card_index == 0" in content
    assert "replacement = self._wrap_plain_card(" in content
    assert "return CollapsibleCard(title, card, expanded=expanded, parent=parent)" in content


def test_qt_secondary_sections_default_to_collapsed_and_remove_body_space():
    content = Path("dpo4000_utils/gui_qt/collapsible_window.py").read_text(encoding="utf-8")

    assert "def _collapsible_section(self, title: str, content: QWidget, *, expanded: bool = False)" in content
    assert 'self._content_shell.setVisible(expanded)' in content
    assert '_COLLAPSED_OBJECT_NAME = "InlineCollapsibleCardCollapsed"' in content
    assert "self.setMinimumHeight(0)" in content
    assert "self.updateGeometry()" in content
