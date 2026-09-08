"""Compatibility adapter for the mature v0.7 feature surface.

The v0.8 production window never inherits from the historical window stack. The
old stack is instantiated behind this one adapter while individual pages and
cross-cutting responsibilities are migrated into composition controllers. This
module is intentionally the only composition module allowed to import a legacy
``*_window`` implementation.
"""

from __future__ import annotations

from pathlib import Path

from ..milestone_a_window import QtScopeWindow as MilestoneAFeatureWindow
from .pages import build_connection_page


class ComposedFeatureSurface(MilestoneAFeatureWindow):
    """Compatibility surface whose migrated pages are owned by composition."""

    def _build_connection_tab(self):
        """Use the native composed Connection page in the production surface."""
        return build_connection_page(self)

    def _build_logger_tab(self):
        """Build the legacy Logger page atomically from the composition boundary.

        Several historical Logger source-card builders call ``_logger_mode_changed``
        while the page is only partially assembled. That method cascades into the
        most-derived status refresh, whose older layers assume that later health and
        acquisition widgets already exist. Suppress those intermediate refreshes and
        issue exactly one refresh once every Logger card has been created.
        """
        self._composition_building_logger_tab = True
        try:
            page = super()._build_logger_tab()
        finally:
            self._composition_building_logger_tab = False
        self._logger_refresh_status()
        return page

    def _logger_refresh_status(self) -> None:
        """Defer legacy Logger status projection until its page is fully built."""
        if getattr(self, "_composition_building_logger_tab", False):
            return
        super()._logger_refresh_status()


class LegacyFeatureSurface:
    """Own the mature feature widget used during the incremental migration boundary."""

    def __init__(self, preferences_path: str | Path | None = None) -> None:
        self.widget = ComposedFeatureSurface(preferences_path=preferences_path)

    def close(self) -> bool:
        """Run the mature surface shutdown chain."""
        return bool(self.widget.close())


__all__ = ["ComposedFeatureSurface", "LegacyFeatureSurface"]
