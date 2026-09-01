"""Collapsible cards and lazily-built control pages, exercised rather than described."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtCore import QEvent, QPoint, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QLabel, QWidget  # noqa: E402

from dpo4000_utils.gui_qt.collapsible_window import CollapsibleCard  # noqa: E402
from dpo4000_utils.gui_qt.display_window import CONTROL_PAGE_BUILDERS  # noqa: E402


def _click(widget, position: QPoint) -> None:
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        position,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    widget.mousePressEvent(event)


# ----------------------------------------------------------------------
# CollapsibleCard
# ----------------------------------------------------------------------
def test_card_header_click_toggles_the_body(qt_app):
    content = QLabel("body")
    card = CollapsibleCard("Demo", content, expanded=True)
    try:
        assert card._content_shell.isVisibleTo(card)

        _click(card, card._header.geometry().center())
        assert not card._content_shell.isVisibleTo(card)

        _click(card, card._header.geometry().center())
        assert card._content_shell.isVisibleTo(card)
    finally:
        card.deleteLater()


def test_clicking_the_body_does_not_collapse_the_card(qt_app):
    content = QLabel("body")
    card = CollapsibleCard("Demo", content, expanded=True)
    card.resize(200, 200)
    try:
        body_point = QPoint(10, card._header.geometry().bottom() + 20)
        _click(card, body_point)
        assert card._content_shell.isVisibleTo(card), "only the header should toggle"
    finally:
        card.deleteLater()


def test_collapsed_card_uses_the_collapsed_object_name_for_styling(qt_app):
    card = CollapsibleCard("Demo", QLabel("body"), expanded=True)
    try:
        assert card.objectName() == CollapsibleCard._EXPANDED_OBJECT_NAME
        card.set_expanded(False)
        assert card.objectName() == CollapsibleCard._COLLAPSED_OBJECT_NAME
    finally:
        card.deleteLater()


def test_collapsed_card_gives_up_its_body_height(qt_app):
    card = CollapsibleCard("Demo", QLabel("body" * 40), expanded=True)
    try:
        card.show()
        qt_app.processEvents()
        expanded_hint = card.sizeHint().height()

        card.set_expanded(False)
        qt_app.processEvents()
        collapsed_hint = card.sizeHint().height()

        assert collapsed_hint < expanded_hint, "a collapsed card must not reserve body space"
    finally:
        card.close()
        card.deleteLater()


def test_card_is_a_child_widget_not_a_stray_top_level_window(qt_app):
    parent = QWidget()
    card = CollapsibleCard("Demo", QLabel("body"), parent=parent)
    try:
        assert card.parent() is parent
        assert not card.isWindow(), "cards must never become separate windows"
    finally:
        parent.deleteLater()


# ----------------------------------------------------------------------
# Lazy control pages
# ----------------------------------------------------------------------
def test_only_the_first_page_is_built_up_front(make_window):
    window = make_window()

    assert window._lazy_control_pages_built[0] is True
    assert not any(window._lazy_control_pages_built[1:])
    assert len(window._lazy_control_pages_built) == len(CONTROL_PAGE_BUILDERS)


def test_selecting_a_page_builds_it_once(make_window):
    window = make_window()

    window._select_drawer_page(4)
    assert window._lazy_control_pages_built[4]
    first = window.control_stack.widget(4)

    window._select_drawer_page(4)
    assert window.control_stack.widget(4) is first, "page was rebuilt on second visit"


def test_building_a_page_replaces_its_placeholder(make_window):
    window = make_window()

    placeholder = window.control_stack.widget(4)
    assert placeholder.objectName().startswith("LazyControlPagePlaceholder")

    window._ensure_control_page_built(4)
    assert window.control_stack.widget(4) is not placeholder
    assert not window.control_stack.widget(4).objectName().startswith("LazyControlPagePlaceholder")


def test_page_cards_become_collapsible_with_a_primary_card_open(make_window):
    window = make_window()
    window._select_drawer_page(1)

    page = window.control_stack.widget(1)
    cards = page.findChildren(CollapsibleCard)
    assert cards, "page cards were not made collapsible"
    assert any(card._expanded for card in cards), "every card on the page starts collapsed"


def test_preferences_are_applied_once_and_then_leave_live_edits_alone(make_window):
    """Re-running preference application must not reset what the user typed."""
    window = make_window()
    window._select_drawer_page(5)
    assert window._lazy_control_pages_preferences_applied[5]

    window.png_prefix.setText("typed_by_user_")
    # This is the path taken whenever another page is built later on.
    window._apply_preferences_to_unapplied_pages()

    assert window.png_prefix.text() == "typed_by_user_"


def test_a_page_built_later_still_receives_its_preferences(make_window):
    window = make_window()
    assert not window._lazy_control_pages_preferences_applied[5]

    window._select_drawer_page(5)

    assert window._lazy_control_pages_preferences_applied[5]
    assert window.png_prefix.text(), "a freshly built page should get stored preferences"
