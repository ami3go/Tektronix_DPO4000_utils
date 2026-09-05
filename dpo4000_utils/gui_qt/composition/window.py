"""Shallow composition-first production window for DPO4000 Desk v0.8."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMainWindow

from .legacy_surface import LegacyFeatureSurface
from .services import (
    LifecycleController,
    LogController,
    OutputPathController,
    PageController,
    PreferencesController,
    ScopeDispatchController,
    WindowChromeController,
)


class QtScopeWindow(QMainWindow):
    """Production v0.8 shell with controllers instead of feature-window inheritance.

    The mature v0.7 feature surface is embedded as a compatibility widget while
    page construction/navigation and cross-cutting services are routed through
    explicit composed controllers. The launched class therefore has a stable,
    shallow Qt MRO; historical ``QtScopeWindow`` subclasses are no longer
    ancestors of the production shell.
    """

    def __init__(self, preferences_path: str | Path | None = None) -> None:
        super().__init__()

        adapter = LegacyFeatureSurface(preferences_path=preferences_path)
        surface = adapter.widget
        self._legacy_adapter = adapter
        self._feature_surface = surface

        title = surface.windowTitle()
        size = surface.size()
        style_sheet = surface.styleSheet()
        frameless = bool(surface.windowFlags() & Qt.WindowType.FramelessWindowHint)

        surface.setParent(self)
        surface.setWindowFlags(Qt.WindowType.Widget)
        self.setCentralWidget(surface)
        self.setWindowTitle(title)
        self.resize(size)
        self.setStyleSheet(style_sheet)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, frameless)

        # Capture mature delegates exactly once, then route all dynamic calls
        # through explicit composition services.
        self.log_controller = LogController(surface._append_log)
        self.scope_controller = ScopeDispatchController(surface._run_action)
        self.page_controller = PageController(
            surface._select_drawer_page,
            surface._ensure_control_page_built,
        )
        self.output_controller = OutputPathController(
            surface._configured_output_folder,
            surface._build_output_path,
        )
        self.preferences_controller = PreferencesController(
            collect_delegate=surface._collect_preferences,
            apply_delegate=surface._apply_preferences,
            preferences_path=getattr(surface, "_preferences_path", preferences_path),
            log=self.log_controller,
        )
        self.lifecycle_controller = LifecycleController(
            surface=surface,
            preferences=self.preferences_controller,
        )
        self.window_chrome = WindowChromeController(self, surface)

        surface._append_log = self.log_controller.append
        surface._run_action = self.scope_controller.run_action
        surface._ensure_control_page_built = self.page_controller.ensure_built
        surface._select_drawer_page = self.page_controller.select
        surface._configured_output_folder = self.output_controller.configured_folder
        surface._build_output_path = self.output_controller.build_path
        surface._collect_preferences = self.preferences_controller.collect
        surface._apply_preferences = self.preferences_controller.apply
        surface._save_preferences_safely = self.preferences_controller.save

        self.window_chrome.install()
        surface.show()

    @property
    def feature_surface(self):
        """Return the compatibility feature widget for migration/testing only."""
        return self._feature_surface

    @property
    def pages(self):
        """Named composed page controllers for Connection through Log."""
        return self.page_controller.pages

    def statusBar(self):  # noqa: N802 - Qt API name.
        """Expose the mature status strip as the shell status bar contract."""
        surface = self.__dict__.get("_feature_surface")
        if surface is not None:
            return surface.statusBar()
        return QMainWindow.statusBar(self)

    def __getattr__(self, name: str):
        """Compatibility delegation for existing GUI callers during v0.8 migration."""
        try:
            surface = object.__getattribute__(self, "_feature_surface")
        except AttributeError as exc:
            raise AttributeError(name) from exc
        try:
            return getattr(surface, name)
        except AttributeError as exc:
            raise AttributeError(name) from exc

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API name.
        self.lifecycle_controller.close_surface()
        event.accept()


__all__ = ["QtScopeWindow"]
