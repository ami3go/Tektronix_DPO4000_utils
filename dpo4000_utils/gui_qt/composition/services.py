"""Composition controllers used by the v0.8 DPO4000 Desk production shell."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QApplication, QToolButton, QWidget

from ...gui.preferences import GuiPreferences, save_preferences

TITLEBAR_DRAG_SURFACE_PROPERTY = "titlebarDragSurface"
TITLEBAR_DOUBLE_CLICK_SURFACE_PROPERTY = "titlebarDoubleClickSurface"
DEFAULT_PAGE_TITLES = (
    "Connection",
    "Channels",
    "Measurement",
    "Trigger",
    "Acquisition",
    "File",
    "Display",
    "Log",
)


class ScopeDispatchController:
    """Explicit production dependency for all feature-surface scope dispatch."""

    def __init__(self, delegate: Callable[..., Any]) -> None:
        self._delegate = delegate

    def run_action(
        self,
        description: str,
        callback: Callable[[Any], object],
        *,
        on_success: Callable[[object], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
        retain_session: bool = False,
    ) -> Any:
        return self._delegate(
            description,
            callback,
            on_success=on_success,
            on_error=on_error,
            retain_session=retain_session,
        )


class FeaturePageController:
    """One named page in the composed production page registry."""

    def __init__(self, owner: "PageController", index: int, title: str) -> None:
        self._owner = owner
        self.index = int(index)
        self.title = str(title)

    def ensure_built(self) -> Any:
        return self._owner.ensure_built(self.index)

    def activate(self) -> Any:
        return self._owner.select(self.index)


class PageController:
    """Own lazy page construction and navigation independently of window inheritance."""

    def __init__(
        self,
        select_delegate: Callable[[int], Any],
        ensure_delegate: Callable[[int], Any],
        *,
        titles: Sequence[str] = DEFAULT_PAGE_TITLES,
    ) -> None:
        self._select_delegate = select_delegate
        self._ensure_delegate = ensure_delegate
        self.current_index = 0
        self.pages = tuple(
            FeaturePageController(self, index, title)
            for index, title in enumerate(titles)
        )
        self.by_title = {page.title: page for page in self.pages}

    def ensure_built(self, index: int) -> Any:
        return self._ensure_delegate(int(index))

    def select(self, index: int) -> Any:
        self.current_index = int(index)
        return self._select_delegate(self.current_index)


class LogController:
    """Stable logging facade shared by composed feature controllers."""

    def __init__(self, delegate: Callable[[str], Any]) -> None:
        self._delegate = delegate

    def append(self, message: str) -> Any:
        return self._delegate(str(message))


class OutputPathController:
    """Own output-folder/path requests used by GUI features."""

    def __init__(
        self,
        folder_delegate: Callable[..., Path],
        path_delegate: Callable[[str], Path],
    ) -> None:
        self._folder_delegate = folder_delegate
        self._path_delegate = path_delegate

    def configured_folder(self, *, create: bool = True) -> Path:
        return Path(self._folder_delegate(create=create))

    def build_path(self, kind: str) -> Path:
        return Path(self._path_delegate(str(kind)))


class PreferencesController:
    """Own persistence while reusing the mature widget mapping during migration."""

    def __init__(
        self,
        *,
        collect_delegate: Callable[[], GuiPreferences],
        apply_delegate: Callable[[GuiPreferences], Any],
        preferences_path: str | Path | None,
        log: LogController,
    ) -> None:
        self._collect_delegate = collect_delegate
        self._apply_delegate = apply_delegate
        self._path = Path(preferences_path) if preferences_path is not None else None
        self._log = log

    def collect(self) -> GuiPreferences:
        return self._collect_delegate()

    def apply(self, preferences: GuiPreferences) -> Any:
        return self._apply_delegate(preferences)

    def save(self) -> Path | None:
        try:
            return save_preferences(self.collect(), self._path)
        except Exception as exc:  # noqa: BLE001 - close must remain safe on filesystem failure.
            self._log.append(f"Could not save GUI preferences: {exc}")
            return None


class WindowChromeController(QObject):
    """Own frameless-window controls and drag behavior for the composed shell."""

    def __init__(self, host, surface) -> None:
        super().__init__(host)
        self._host = host
        self._surface = surface
        self._drag_start = None
        self._drag_offset = None
        self._drag_active = False

    @staticmethod
    def _global_position(event):
        if hasattr(event, "globalPosition"):
            return event.globalPosition().toPoint()
        return event.globalPos()

    def install(self) -> None:
        """Replace legacy top-level window handlers with host-owned composition handlers."""
        for widget in self._surface.findChildren(QWidget):
            if widget.property(TITLEBAR_DRAG_SURFACE_PROPERTY):
                widget.removeEventFilter(self._surface)
                widget.installEventFilter(self)

        maximize = getattr(self._surface, "titlebar_maximize_button", None)
        for button in self._surface.findChildren(QToolButton):
            object_name = button.objectName()
            if object_name == "TitlebarCloseButton":
                self._rewire(button, self._host.close)
            elif object_name == "TitlebarWindowButton":
                if button is maximize or button.text() in {"□", "❐"}:
                    self._rewire(button, self.toggle_maximized)
                elif button.text() in {"—", "-"}:
                    self._rewire(button, self._host.showMinimized)

        self._surface._toggle_maximized = self.toggle_maximized
        self._surface._sync_maximize_button = self.sync_maximize_button
        self.sync_maximize_button()

    @staticmethod
    def _rewire(button: QToolButton, callback: Callable[[], None]) -> None:
        try:
            button.clicked.disconnect()
        except (RuntimeError, TypeError):
            pass
        button.clicked.connect(callback)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt API name.
        if not isinstance(watched, QWidget) or not watched.property(
            TITLEBAR_DRAG_SURFACE_PROPERTY
        ):
            return False

        event_type = event.type()
        if (
            event_type == QEvent.Type.MouseButtonPress
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self._drag_start = self._global_position(event)
            self._drag_offset = self._drag_start - self._host.frameGeometry().topLeft()
            self._drag_active = False
            return False

        if (
            event_type == QEvent.Type.MouseMove
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            if self._drag_start is None or self._drag_offset is None:
                return False
            current = self._global_position(event)
            moved = (current - self._drag_start).manhattanLength()
            if not self._drag_active and moved < QApplication.startDragDistance():
                return False
            self._drag_active = True
            self._start_window_move(event)
            return True

        if event_type == QEvent.Type.MouseButtonRelease:
            consumed = self._drag_active
            self._reset_drag()
            return consumed

        if (
            event_type == QEvent.Type.MouseButtonDblClick
            and watched.property(TITLEBAR_DOUBLE_CLICK_SURFACE_PROPERTY)
            and event.button() == Qt.MouseButton.LeftButton
        ):
            self.toggle_maximized()
            event.accept()
            return True

        return False

    def _start_window_move(self, event) -> None:
        if self._host.isMaximized():
            self._host.showNormal()
            self.sync_maximize_button()

        handle = self._host.windowHandle()
        if handle is not None and hasattr(handle, "startSystemMove"):
            try:
                if handle.startSystemMove():
                    return
            except RuntimeError:
                pass

        if self._drag_offset is not None:
            self._host.move(self._global_position(event) - self._drag_offset)

    def _reset_drag(self) -> None:
        self._drag_start = None
        self._drag_offset = None
        self._drag_active = False

    def toggle_maximized(self) -> None:
        if self._host.isMaximized():
            self._host.showNormal()
        else:
            self._host.showMaximized()
        self.sync_maximize_button()

    def sync_maximize_button(self) -> None:
        button = getattr(self._surface, "titlebar_maximize_button", None)
        if button is not None:
            button.setText("❐" if self._host.isMaximized() else "□")


class LifecycleController:
    """Coordinate shutdown of the composed host and mature feature surface."""

    def __init__(self, *, surface, preferences: PreferencesController) -> None:
        self._surface = surface
        self._preferences = preferences
        self._closed = False

    def close_surface(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._surface.close()


__all__ = [
    "FeaturePageController",
    "LifecycleController",
    "LogController",
    "OutputPathController",
    "PageController",
    "PreferencesController",
    "ScopeDispatchController",
    "WindowChromeController",
]
