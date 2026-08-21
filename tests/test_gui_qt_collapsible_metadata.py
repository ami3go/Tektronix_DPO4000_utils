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
    assert "card header itself toggles the body" in content
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


def test_qt_collapsed_cards_are_header_only_without_empty_body_space():
    content = Path("dpo4000_utils/gui_qt/collapsible_window.py").read_text(encoding="utf-8")
    theme = Path("dpo4000_utils/gui_qt/theme.qss").read_text(encoding="utf-8")

    assert "_COLLAPSED_OBJECT_NAME = \"InlineCollapsibleCardCollapsed\"" in content
    assert "self.setObjectName(self._EXPANDED_OBJECT_NAME if expanded else self._COLLAPSED_OBJECT_NAME)" in content
    assert "self._content.setVisible(expanded)" in content
    assert "self._layout.setContentsMargins(0, 0, 0, 0)" in content
    assert "self.setMinimumHeight(self._HEADER_HEIGHT)" in content
    assert "self.setMaximumHeight(self._HEADER_HEIGHT)" in content
    assert "self.setMaximumHeight(16_777_215)" in content
    assert "self.updateGeometry()" in content
    assert "QGroupBox#InlineCollapsibleCardCollapsed" in theme
    assert "QGroupBox#InlineCollapsibleCardCollapsed {" in theme
    assert "padding: 34px 0 0 0;" in theme
    assert "QGroupBox#InlineCollapsibleCardCollapsed::title" in theme
    assert "border-bottom: 0;" in theme


def test_qt_collapsible_cards_match_normal_card_frame():
    theme = Path("dpo4000_utils/gui_qt/theme.qss").read_text(encoding="utf-8")

    shared_frame_block = theme[
        theme.index("QGroupBox#InlineCollapsibleCard,"):theme.index("QGroupBox#InlineCollapsibleCard {")
    ]
    assert "background: #1f2937;" in shared_frame_block
    assert "border: 1px solid #374151;" in shared_frame_block
    assert "border-radius: 8px;" in shared_frame_block
    assert "margin-top: 0;" in shared_frame_block
