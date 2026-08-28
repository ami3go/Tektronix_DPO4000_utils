"""PySide6 UI-practice layer for status, shortcuts, and safe controls."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .enhanced_window import QtScopeWindow as CompactQtScopeWindow
from .main_window import APP_TITLE, DEFAULT_DRAWER_WIDTH, DRAWER_PAGE_TITLES

SCOPE_ACTION_CALLBACKS = {
    "capture_preview",
    "save_png_image",
    "save_csv",
    "save_settings",
    "restore_settings",
    "read_labels",
    "apply_labels",
    "read_channel_configuration",
    "apply_channel_configuration",
    "read_math_configuration",
    "apply_math_configuration",
    "read_acquisition_setup",
    "apply_acquisition_setup",
    "add_measurement",
    "read_measurement_value",
    "clear_measurement_slot",
    "clear_all_measurements",
    "read_trigger_level",
    "apply_trigger_level",
    "read_horizontal_position",
    "set_horizontal_position",
    "set_horizontal_position_to_zero",
    "apply_edge_trigger",
    "run_acquisition",
    "stop_acquisition",
    "single_acquisition",
    "continuous_acquisition",
    "force_trigger",
}
SAFE_UI_CALLBACKS = {
    "test_connection",
    "refresh_visa_resources",
    "apply_ethernet_resource",
    "pick_output_folder",
    "copy_preview",
    "show_control_drawer",
    "hide_control_drawer",
    "toggle_drawer_pin",
    "toggle_compact_mode",
    "mark_disconnected",
    "retry_connection",
}
SHORTCUTS = (
    ("F5", "Capture preview", "capture_preview", True),
    ("Ctrl+S", "Save PNG", "save_png_image", True),
    ("Ctrl+Shift+S", "Save CSV", "save_csv", True),
    ("F6", "Run acquisition", "run_acquisition", True),
    ("F7", "Stop acquisition", "stop_acquisition", True),
    ("F8", "Single acquisition", "single_acquisition", True),
)
PAGE_SHORTCUTS = (
    ("Ctrl+1", 0, "Connection"),
    ("Ctrl+2", 1, "Channels"),
    ("Ctrl+3", 2, "Measurement"),
    ("Ctrl+4", 3, "Trigger"),
    ("Ctrl+5", 4, "Settings"),
    ("Ctrl+6", 5, "Log"),
)
QUICK_TOOLTIPS = {
    "IDN": "Test connection and unlock scope controls",
    "Capture": "F5 · Capture scope screen preview",
    "Copy": "Ctrl+C on preview · Copy current preview image",
    "PNG": "Ctrl+S · Save scope screen as PNG",
    "CSV": "Ctrl+Shift+S · Save enabled channels to CSV",
    "Run": "F6 · Start acquisition",
    "Stop": "F7 · Stop acquisition",
    "Single": "F8 · Start single acquisition",
    "Force": "Force one trigger event",
}


class QtScopeWindow(CompactQtScopeWindow):
    """Qt window with status strip, recovery buttons, guarded actions, and tabs."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._scope_controls: list[QWidget] = []
        self._shortcuts: list[QShortcut] = []
        self._connection_ok = False
        self._operation_active = False
        self._last_idn = "Not tested"
        self._last_action = "Ready"
        self._acquisition_state = "Unknown"
        super().__init__(*args, **kwargs)
        self._configure_bottom_status_bar()
        self._install_global_shortcuts()
        self._update_scope_control_enabled()
        self._update_status_strip()

    # ------------------------------------------------------------------
    # Tabbed top-level layout
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        """Build preview plus tabbed controls; the remote drawer is not used."""
        central = QWidget(self)
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 18, 18, 12)
        root.setSpacing(14)
        self.setCentralWidget(central)

        header = QHBoxLayout()
        title = QLabel(APP_TITLE)
        title.setObjectName("TitleLabel")
        subtitle = QLabel("PySide6 testing branch · tabbed controls · Tkinter GUI remains available")
        subtitle.setObjectName("MutedLabel")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.compact_mode_button = QToolButton()
        self.compact_mode_button.setObjectName("CompactModeButton")
        self.compact_mode_button.setCheckable(True)
        self.compact_mode_button.setChecked(True)
        self.compact_mode_button.setText("Compact")
        self.compact_mode_button.setToolTip("Hide advanced tab sections")
        self.compact_mode_button.clicked.connect(self.toggle_compact_mode)
        header.addWidget(title, 1)
        header.addWidget(subtitle, 1)
        header.addWidget(self.compact_mode_button)
        root.addLayout(header)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setObjectName("MainSplitter")
        root.addWidget(self.main_splitter, 1)

        preview_card = self._build_preview_card()
        preview_card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.main_splitter.addWidget(preview_card)

        self.control_tabs = self._build_control_tabs()
        self.control_tabs.setMinimumWidth(420)
        self.control_tabs.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.main_splitter.addWidget(self.control_tabs)
        self.main_splitter.setStretchFactor(0, 3)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([810, DEFAULT_DRAWER_WIDTH])

        self.setStatusBar(QStatusBar())

    def _build_control_tabs(self) -> QTabWidget:
        tabs = QTabWidget()
        tabs.setObjectName("ControlTabs")
        tabs.setDocumentMode(True)
        tabs.setTabPosition(QTabWidget.TabPosition.North)
        tabs.addTab(self._build_connection_tab(), DRAWER_PAGE_TITLES[0])
        tabs.addTab(self._build_channels_tab(), DRAWER_PAGE_TITLES[1])
        tabs.addTab(self._build_measurement_tab(), DRAWER_PAGE_TITLES[2])
        tabs.addTab(self._build_trigger_tab(), DRAWER_PAGE_TITLES[3])
        tabs.addTab(self._build_settings_tab(), DRAWER_PAGE_TITLES[4])
        tabs.addTab(self._build_log_tab(), DRAWER_PAGE_TITLES[5])
        return tabs

    def _select_drawer_page(self, index: int) -> None:
        """Keep old page-switch callers working after replacing the drawer with tabs."""
        tabs = getattr(self, "control_tabs", None)
        if tabs is None or index < 0 or index >= tabs.count():
            return
        tabs.setCurrentIndex(index)
        self.statusBar().showMessage(f"Selected {tabs.tabText(index)} tab")

    def show_control_drawer(self) -> None:
        """Compatibility no-op: controls are tabs now, not a hideable drawer."""
        tabs = getattr(self, "control_tabs", None)
        if tabs is not None:
            tabs.setVisible(True)
        self.statusBar().showMessage("Controls are shown as tabs")

    def hide_control_drawer(self) -> None:
        """Compatibility no-op: the drawer has been removed from the launched UI."""
        self.statusBar().showMessage("Control drawer removed; use the tabs")

    def toggle_drawer_pin(self) -> None:
        """Compatibility no-op for callers from older drawer code."""
        self.statusBar().showMessage("Control drawer removed; tabs are always available")

    # ------------------------------------------------------------------
    # Button registration and status shell
    # ------------------------------------------------------------------
    def _button(self, text: str, callback: Callable[[], None]) -> QPushButton:
        button = super()._button(text, callback)
        self._register_button_if_scope_action(button, callback)
        self._apply_button_tooltip(button, text, callback)
        return button

    def _accent_button(self, text: str, callback: Callable[[], None]) -> QPushButton:
        button = super()._accent_button(text, callback)
        self._register_button_if_scope_action(button, callback)
        self._apply_button_tooltip(button, text, callback)
        return button

    def _quick_button(self, text: str, callback: Callable[[], None], *, accent: bool = False) -> QToolButton:
        button = super()._quick_button(text, callback, accent=accent)
        self._register_button_if_scope_action(button, callback)
        tooltip = QUICK_TOOLTIPS.get(text)
        if tooltip:
            button.setToolTip(tooltip)
        return button

    def _register_button_if_scope_action(self, button: QWidget, callback: Callable[..., object]) -> None:
        if self._callback_requires_scope(callback):
            button.setProperty("scopeAction", True)
            self._scope_controls.append(button)

    def _callback_requires_scope(self, callback: Callable[..., object]) -> bool:
        name = getattr(callback, "__name__", "")
        if name in SAFE_UI_CALLBACKS:
            return False
        if name in SCOPE_ACTION_CALLBACKS:
            return True
        return name == "<lambda>"

    def _apply_button_tooltip(self, button: QWidget, text: str, callback: Callable[..., object]) -> None:
        name = getattr(callback, "__name__", "")
        shortcut_by_name = {
            "capture_preview": "F5",
            "save_png_image": "Ctrl+S",
            "save_csv": "Ctrl+Shift+S",
            "run_acquisition": "F6",
            "stop_acquisition": "F7",
            "single_acquisition": "F8",
            "test_connection": "Test IDN first to unlock controls",
            "copy_preview": "Ctrl+C on preview",
        }
        shortcut = shortcut_by_name.get(name)
        if shortcut and not button.toolTip():
            button.setToolTip(f"{shortcut} · {text}")

    def _build_preview_card(self):
        card = super()._build_preview_card()
        layout = card.layout()
        if layout is not None:
            layout.insertWidget(0, self._build_status_strip())
        return card

    def _build_status_strip(self) -> QWidget:
        """Build the compact scope-state strip above the preview.

        Resource and IDN are intentionally kept out of this strip; they live in
        permanent sections of the bottom status bar where long identification
        strings do not compete with the connection badge.
        """
        strip = QWidget()
        strip.setObjectName("ScopeStatusStrip")
        layout = QHBoxLayout(strip)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        self.connection_badge = QLabel("● Not tested")
        self.acquisition_status = QLabel("Acq: unknown")
        self.last_action_status = QLabel("Last: ready")
        for label in (
            self.connection_badge,
            self.acquisition_status,
            self.last_action_status,
        ):
            label.setObjectName("StatusChip")
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            layout.addWidget(label)

        layout.addStretch(1)
        layout.addWidget(self._status_button("Retry", self.retry_connection, "Retest *IDN?"))
        layout.addWidget(self._status_button("Refresh", self.refresh_visa_resources, "Refresh VISA resource list"))
        layout.addWidget(self._status_button("Disconnect", self.mark_disconnected, "Lock scope controls"))
        return strip

    def _configure_bottom_status_bar(self) -> None:
        """Add permanent Resource and IDN sections beside transient status messages."""
        if getattr(self, "_bottom_status_sections_installed", False):
            return

        status = self.statusBar()
        self._bottom_status_sections_installed = True
        self.resource_status = QLabel("Resource: not selected")
        self.idn_status = QLabel("IDN: not tested")

        for label, tooltip, minimum_width, maximum_width in (
            (self.resource_status, "Selected VISA resource", 220, 440),
            (self.idn_status, "Last instrument identification response", 240, 460),
        ):
            label.setObjectName("BottomStatusSection")
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setToolTip(tooltip)
            label.setMinimumWidth(minimum_width)
            label.setMaximumWidth(maximum_width)
            label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        status.addPermanentWidget(self._bottom_status_separator())
        status.addPermanentWidget(self.resource_status)
        status.addPermanentWidget(self._bottom_status_separator())
        status.addPermanentWidget(self.idn_status)

    @staticmethod
    def _bottom_status_separator() -> QFrame:
        separator = QFrame()
        separator.setObjectName("BottomStatusSeparator")
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Plain)
        return separator

    def _status_button(self, text: str, callback: Callable[[], None], tooltip: str) -> QToolButton:
        button = QToolButton()
        button.setObjectName("StatusActionButton")
        button.setText(text)
        button.setToolTip(tooltip)
        button.clicked.connect(callback)
        return button

    def _build_connection_tab(self) -> QWidget:
        page = super()._build_connection_tab()
        try:
            self.resource.currentTextChanged.connect(lambda _text: self._mark_connection_stale("Resource changed"))
            self.eth_host.textChanged.connect(lambda _text: self._mark_connection_stale("Ethernet host changed"))
            self.eth_port.textChanged.connect(lambda _text: self._mark_connection_stale("Ethernet port changed"))
            self.eth_protocol.currentTextChanged.connect(lambda _text: self._mark_connection_stale("Ethernet protocol changed"))
            self.usb_mode.toggled.connect(lambda _checked: self._mark_connection_stale("Connection mode changed"))
            self.eth_mode.toggled.connect(lambda _checked: self._mark_connection_stale("Connection mode changed"))
        except Exception:
            pass
        return page

    # ------------------------------------------------------------------
    # Status and command behavior
    # ------------------------------------------------------------------
    def retry_connection(self) -> None:
        self.test_connection()

    def mark_disconnected(self) -> None:
        self._connection_ok = False
        self._last_idn = "Not tested"
        self._acquisition_state = "Unknown"
        self._last_action = "Disconnected"
        self._append_log("Scope controls locked by user")
        self._update_scope_control_enabled()
        self._update_status_strip()
        self.statusBar().showMessage("Scope controls locked")

    def _mark_connection_stale(self, reason: str) -> None:
        if self._operation_active:
            return
        if self._connection_ok:
            self._append_log(f"Connection marked stale: {reason}")
        self._connection_ok = False
        self._last_idn = "Retest required"
        self._last_action = reason
        self._update_scope_control_enabled()
        self._update_status_strip()

    def _set_connection_badge_state(self, state: str) -> None:
        label = getattr(self, "connection_badge", None)
        if label is None:
            return
        label.setObjectName(f"StatusBadge{state}")
        label.style().unpolish(label)
        label.style().polish(label)

    def _resource_summary(self) -> str:
        try:
            if getattr(self, "eth_mode", None) is not None and self.eth_mode.isChecked():
                resource = self.generated_resource.text().strip() or self.eth_host.text().strip()
            else:
                resource = self.resource.currentText().strip()
        except Exception:
            resource = ""
        if not resource:
            return "Resource: not selected"
        if len(resource) > 52:
            resource = resource[:24] + "…" + resource[-24:]
        return f"Resource: {resource}"

    def _update_status_strip(self) -> None:
        if not hasattr(self, "connection_badge"):
            return
        if self._operation_active:
            self.connection_badge.setText("● Busy")
            self._set_connection_badge_state("Busy")
        elif self._connection_ok:
            self.connection_badge.setText("● Connected")
            self._set_connection_badge_state("Ok")
        else:
            self.connection_badge.setText("● Not tested")
            self._set_connection_badge_state("Warn")

        if hasattr(self, "resource_status"):
            self.resource_status.setText(self._resource_summary())
        if hasattr(self, "idn_status"):
            self.idn_status.setText(f"IDN: {self._shorten_status_text(self._last_idn, 54)}")
        self.acquisition_status.setText(f"Acq: {self._acquisition_state}")
        self.last_action_status.setText(f"Last: {self._shorten_status_text(self._last_action, 42)}")

    @staticmethod
    def _shorten_status_text(text: str, length: int) -> str:
        if len(text) <= length:
            return text
        return text[: length - 1] + "…"

    def _update_scope_control_enabled(self) -> None:
        enabled = self._connection_ok and not self._operation_active
        for button in getattr(self, "_scope_controls", []):
            try:
                button.setEnabled(enabled)
            except RuntimeError:
                pass

    def _guarded_scope_call(self, callback: Callable[[], None], label: str) -> None:
        if not self._connection_ok:
            self._last_action = "Test IDN first"
            self._update_status_strip()
            self._message(label, "Test IDN first to unlock scope controls.", error=True)
            return
        callback()

    def test_connection(self) -> None:
        result = self._run_action("Testing scope connection", lambda scope: scope.scope.query("*IDN?").strip())
        if result is not None:
            self._last_idn = str(result)
            self._connection_ok = True
            self._last_action = "IDN OK"
            self._update_scope_control_enabled()
            self._update_status_strip()
            self._message("Scope IDN", str(result))

    def _run_action(self, description: str, callback: Callable[[Any], object]) -> object | None:
        self._operation_active = True
        self._last_action = description
        self.statusBar().showMessage(description)
        self._append_log(description)
        self._update_scope_control_enabled()
        self._update_status_strip()
        try:
            result = self._new_scope_session(callback)
        except Exception as exc:
            self._connection_ok = False
            self._last_action = f"Failed: {description}"
            self.statusBar().showMessage(f"Failed: {description}")
            self._append_log(f"ERROR: {exc}")
            self._operation_active = False
            self._update_scope_control_enabled()
            self._update_status_strip()
            self._message(description, str(exc), error=True)
            return None
        self._connection_ok = True
        self._operation_active = False
        self._last_action = f"Done: {description}"
        self._update_acquisition_state_from_description(description)
        self.statusBar().showMessage(f"Done: {description}")
        if result is not None:
            self._append_log(str(result))
        self._update_scope_control_enabled()
        self._update_status_strip()
        return result

    def _update_acquisition_state_from_description(self, description: str) -> None:
        text = description.lower()
        if "starting acquisition" in text or "continuous" in text:
            self._acquisition_state = "Run"
        elif "stopping acquisition" in text:
            self._acquisition_state = "Stop"
        elif "single acquisition" in text:
            self._acquisition_state = "Single"
        elif "forcing trigger" in text:
            self._acquisition_state = "Force sent"

    # ------------------------------------------------------------------
    # Keyboard shortcuts
    # ------------------------------------------------------------------
    def _install_global_shortcuts(self) -> None:
        for key, label, method_name, requires_scope in SHORTCUTS:
            method = getattr(self, method_name)
            self._make_shortcut(
                key,
                lambda checked=False, callback=method, shortcut_label=label, guarded=requires_scope: (
                    self._guarded_scope_call(callback, shortcut_label) if guarded else callback()
                ),
            )
        self._make_shortcut("Ctrl+L", self._focus_resource_field)
        for key, page, _title in PAGE_SHORTCUTS:
            self._make_shortcut(key, lambda checked=False, index=page: self._select_drawer_page(index))

    def _make_shortcut(self, sequence: str, callback: Callable[[], None]) -> None:
        shortcut = QShortcut(QKeySequence(sequence), self)
        shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        shortcut.activated.connect(callback)
        self._shortcuts.append(shortcut)

    def _focus_resource_field(self) -> None:
        self._select_drawer_page(0)
        try:
            self.resource.setFocus()
            self.resource.lineEdit().selectAll() if self.resource.lineEdit() is not None else None
        except Exception:
            pass


__all__ = ["QtScopeWindow"]
