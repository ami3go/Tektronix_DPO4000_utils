from __future__ import annotations

from pathlib import Path


def test_qt_runner_launches_measurement_window():
    runner = Path("dpo4000_utils/gui_qt/runner.py").read_text(encoding="utf-8")
    package_init = Path("dpo4000_utils/gui_qt/__init__.py").read_text(encoding="utf-8")

    assert "from .measurement_window import QtScopeWindow" in runner
    assert "from .measurement_window import QtScopeWindow" in package_init
    assert "from .display_window import QtScopeWindow" not in runner
    assert "from .display_window import QtScopeWindow" not in package_init
    assert "from .collapsible_window import QtScopeWindow" not in runner
    assert "from .collapsible_window import QtScopeWindow" not in package_init


def test_qt_stable_window_runs_scope_actions_on_worker_thread():
    content = Path("dpo4000_utils/gui_qt/stable_window.py").read_text(encoding="utf-8")
    worker = Path("dpo4000_utils/gui_qt/scope_worker.py").read_text(encoding="utf-8")

    assert "class QtScopeWindow(MatureQtScopeWindow)" in content
    assert "def _run_action" in content
    assert "start_scope_worker" in content
    assert "QEventLoop" in content
    assert "_run_snapshot_scope_session" in content
    assert "DPO4054(resource, auto_connect=False)" in content
    assert "instrument.timeout = timeout_ms" in content
    assert "class ScopeWorker(QRunnable)" in worker
    assert "QThreadPool.globalInstance().start(worker)" in worker


def test_qt_window_chrome_uses_only_window_title_for_app_name():
    content = Path("dpo4000_utils/gui_qt/collapsible_window.py").read_text(encoding="utf-8")

    assert 'WINDOW_TITLE = "Tektronix dpo4000"' in content
    assert "self.setWindowTitle(WINDOW_TITLE)" in content
    assert "def _build_application_menu_bar" in content
    assert 'bar.findChild(QLabel, "ApplicationMenuTitle")' in content
    assert "layout.removeWidget(title)" in content
    assert "title.hide()" in content
    assert "title.deleteLater()" in content
    assert "title.setParent(None)" not in content
    assert "WINDOW_TITLE" in content


def test_qt_collapsible_sections_use_lightweight_card_header_not_extra_button():
    content = Path("dpo4000_utils/gui_qt/collapsible_window.py").read_text(encoding="utf-8")

    assert "class CollapsibleCard(QFrame)" in content
    assert "A lightweight collapsible card" in content
    assert "QFrame" in content
    assert "class CollapsibleCard(QGroupBox)" not in content
    assert "QGroupBox#InlineCollapsibleCard" not in content
    assert "card header itself toggles the body" in content
    assert "mousePressEvent" in content
    assert "self._header.geometry().contains(event.pos())" in content
    assert "self._header.setText((\"▾ \" if expanded else \"▸ \") + self._base_title)" in content
    assert "CollapsibleHeader" not in content
    assert "QToolButton" not in content
    assert "InlineCollapsibleCard" in content
    assert "InlineCollapsibleContent" in content
    assert "parent: QWidget | None = None" in content
    assert "super().__init__(parent)" in content
    assert "self.setWindowFlags(Qt.WindowType.Widget)" in content


def test_qt_lightweight_collapsible_card_styles_are_local_to_launched_window():
    content = Path("dpo4000_utils/gui_qt/collapsible_window.py").read_text(encoding="utf-8")

    assert "PREVIEW_CONTROL_GUTTER_QSS" in content
    assert "QFrame#InlineCollapsibleCard," in content
    assert "QFrame#InlineCollapsibleCardCollapsed" in content
    assert "QLabel#InlineCollapsibleHeader" in content
    assert "QWidget#InlineCollapsibleBody" in content
    assert "QGroupBox#InlineCollapsibleContent" in content
    assert "background: #253142" in content
    assert "border-bottom-left-radius: 7px;" in content


def test_qt_preview_and_control_panel_use_sibling_gutter():
    content = Path("dpo4000_utils/gui_qt/collapsible_window.py").read_text(encoding="utf-8")

    assert "PREVIEW_CONTROL_GUTTER_WIDTH = 12" in content
    assert "PREVIEW_CONTROL_GUTTER_QSS" in content
    assert "def _apply_preview_control_gutter" in content
    assert "self.main_splitter.setHandleWidth(PREVIEW_CONTROL_GUTTER_WIDTH)" in content
    assert "self.main_splitter.setStyleSheet(PREVIEW_CONTROL_GUTTER_QSS)" in content
    assert 'self.findChild(QWidget, "RightControlPanel")' in content
    assert "right_panel.setStyleSheet(PREVIEW_CONTROL_GUTTER_QSS)" in content
    assert "QSplitter#MainSplitter::handle" in content
    assert "width: 12px;" in content
    assert "QSplitter#MainSplitter::handle:hover" in content
    assert "border: 1px solid #2b3544;" in content


def test_qt_control_pages_are_lazy_built_to_avoid_startup_combo_popups():
    content = Path("dpo4000_utils/gui_qt/collapsible_window.py").read_text(encoding="utf-8")

    assert "CONTROL_PAGE_BUILDERS" in content
    assert "QStackedWidget" in content
    assert "Create placeholder pages and build real control pages only when opened." in content
    assert "self._lazy_control_pages_built = [False for _ in CONTROL_PAGE_BUILDERS]" in content
    assert "LazyControlPagePlaceholder" in content
    assert "def _select_drawer_page" in content
    assert "self._ensure_control_page_built(index)" in content
    assert "def _ensure_control_page_built" in content
    assert "builder = getattr(self, CONTROL_PAGE_BUILDERS[index])" in content
    assert "stack.removeWidget(placeholder)" in content
    assert "placeholder.deleteLater()" in content
    assert "stack.insertWidget(index, page)" in content
    assert "self._lazy_control_pages_built[index] = True" in content
    assert "super()._build_control_stack()" not in content


def test_qt_lazy_pages_apply_preferences_once_per_page():
    content = Path("dpo4000_utils/gui_qt/collapsible_window.py").read_text(encoding="utf-8")

    assert "CONNECTION_PAGE_INDEX = 0" in content
    assert "TRIGGER_PAGE_INDEX = 3" in content
    assert "SETTINGS_PAGE_INDEX = 5" in content
    assert "PREFERENCE_PAGE_INDEXES" in content
    assert "self._pending_preferences = None" in content
    assert "self._lazy_control_pages_preferences_applied: list[bool] = []" in content
    assert "self._lazy_control_pages_preferences_applied = [False for _ in CONTROL_PAGE_BUILDERS]" in content
    assert "def _apply_preferences(self, preferences)" in content
    assert "self._pending_preferences = preferences" in content
    assert "def _apply_preferences_to_unapplied_pages" in content
    assert "without overwriting live edits" in content
    assert "def _apply_preferences_to_control_page" in content
    assert "if index == CONNECTION_PAGE_INDEX" in content
    assert "elif index == TRIGGER_PAGE_INDEX" in content
    assert "elif index == SETTINGS_PAGE_INDEX" in content
    assert "self._lazy_control_pages_preferences_applied[index] = True" in content
    assert "def _apply_preferences_to_built_widgets" not in content


def test_qt_collect_preferences_builds_only_preference_pages():
    content = Path("dpo4000_utils/gui_qt/collapsible_window.py").read_text(encoding="utf-8")

    assert "def _collect_preferences" in content
    assert "for index in PREFERENCE_PAGE_INDEXES:" in content
    assert "return super()._collect_preferences()" in content


def test_qt_lazy_pages_build_required_pages_for_quick_actions():
    content = Path("dpo4000_utils/gui_qt/collapsible_window.py").read_text(encoding="utf-8")

    assert "def capture_preview" in content
    assert "self._ensure_control_page_built(TRIGGER_PAGE_INDEX)" in content
    assert "def save_png_image" in content
    assert "def save_csv" in content
    assert "def save_settings" in content
    assert "def restore_settings" in content
    assert "self._ensure_control_page_built(SETTINGS_PAGE_INDEX)" in content


def test_qt_every_direct_card_becomes_collapsible_with_primary_open_by_default():
    content = Path("dpo4000_utils/gui_qt/collapsible_window.py").read_text(encoding="utf-8")

    assert "def _make_page_cards_collapsible" in content
    assert "page.widget() if isinstance(page, QScrollArea) else page" in content
    assert "while index < layout.count():" in content
    assert "if not isinstance(widget, QGroupBox) or isinstance(widget, CollapsibleCard):" in content
    assert "widget.hide()" in content
    assert "layout.removeWidget(widget)" in content
    assert "replacement = self._wrap_plain_card(" in content
    assert "expanded=plain_card_index == 0" in content
    assert "parent=body" in content
    assert "layout.insertWidget(index, replacement)" in content
    assert "replacement.show()" in content
    assert "plain_card_index += 1" in content
    assert "def _wrap_plain_card" in content
    assert "Wrap a normal card so all cards share the same lightweight behavior." in content
    assert "return CollapsibleCard(title, card, expanded=expanded, parent=parent)" in content


def test_qt_startup_does_not_create_parentless_intermediate_widgets():
    content = Path("dpo4000_utils/gui_qt/collapsible_window.py").read_text(encoding="utf-8")

    assert "parent: QWidget" in content
    assert "parent=body" in content
    assert "super().__init__(parent)" in content
    assert "self._header = QLabel(self)" in content
    assert "self._content_shell = QWidget(self)" in content
    assert "card.setWindowFlags(Qt.WindowType.Widget)" in content
    assert "setParent(None)" not in content


def test_qt_secondary_collapsible_sections_are_collapsed_by_default():
    content = Path("dpo4000_utils/gui_qt/collapsible_window.py").read_text(encoding="utf-8")

    assert "def _collapsible_section(self, title: str, content: QWidget, *, expanded: bool = False)" in content
    assert "Secondary cards and explicit" in content
    assert "advanced sections start collapsed" in content


def test_qt_collapsed_cards_are_header_only_without_empty_body_space():
    content = Path("dpo4000_utils/gui_qt/collapsible_window.py").read_text(encoding="utf-8")

    assert "_COLLAPSED_OBJECT_NAME = \"InlineCollapsibleCardCollapsed\"" in content
    assert "self.setObjectName(self._EXPANDED_OBJECT_NAME if expanded else self._COLLAPSED_OBJECT_NAME)" in content
    assert "self._content_shell.setVisible(expanded)" in content
    assert "self._layout.setContentsMargins(0, 0, 0, 0)" in content
    assert "self._header.setMinimumHeight(34)" in content
    assert "self.setMaximumHeight(16_777_215)" in content
    assert "self.setMinimumHeight(0)" in content
    assert "self.updateGeometry()" in content
    assert "QFrame#InlineCollapsibleCardCollapsed QLabel#InlineCollapsibleHeader" in content
    assert "border-bottom: 0;" in content


def test_qt_collapsible_cards_match_normal_card_frame():
    content = Path("dpo4000_utils/gui_qt/collapsible_window.py").read_text(encoding="utf-8")

    shared_frame_block = content[
        content.index("QFrame#InlineCollapsibleCard,"):content.index("QFrame#InlineCollapsibleCard:hover")
    ]
    assert "background: #1f2937;" in shared_frame_block
    assert "border: 1px solid #374151;" in shared_frame_block
    assert "border-radius: 8px;" in shared_frame_block
