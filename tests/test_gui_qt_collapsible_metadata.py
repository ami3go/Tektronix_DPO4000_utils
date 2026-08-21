from __future__ import annotations

from pathlib import Path


def test_qt_runner_launches_clickable_collapsible_window():
    runner = Path("dpo4000_utils/gui_qt/runner.py").read_text(encoding="utf-8")
    package_init = Path("dpo4000_utils/gui_qt/__init__.py").read_text(encoding="utf-8")

    assert "from .collapsible_window import QtScopeWindow" in runner
    assert "from .collapsible_window import QtScopeWindow" in package_init


def test_qt_collapsible_sections_use_card_header_not_extra_button():
    content = Path("dpo4000_utils/gui_qt/collapsible_window.py").read_text(encoding="utf-8")
    theme = Path("dpo4000_utils/gui_qt/theme.qss").read_text(encoding="utf-8")

    assert "class CollapsibleCard(QGroupBox)" in content
    assert "card title/header toggles the body" in content
    assert "mousePressEvent" in content
    assert "event.pos().y() <= self._HEADER_HEIGHT" in content
    assert "self.setTitle((\"▾ \" if expanded else \"▸ \") + self._base_title)" in content
    assert "CollapsibleHeader" not in content
    assert "QToolButton" not in content
    assert "InlineCollapsibleCard" in content
    assert "InlineCollapsibleContent" in content
    assert "CollapsibleCard(title, content, expanded=expanded)" in content
    assert "QGroupBox#InlineCollapsibleCard" in theme
    assert "QGroupBox#InlineCollapsibleCard::title" in theme
    assert "background: #253142" in theme
    assert "QGroupBox#InlineCollapsibleContent" in theme
