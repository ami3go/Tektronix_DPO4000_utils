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


class LegacyFeatureSurface:
    """Own the mature feature widget used during the incremental migration boundary."""

    def __init__(self, preferences_path: str | Path | None = None) -> None:
        self.widget = ComposedFeatureSurface(preferences_path=preferences_path)

    def close(self) -> bool:
        """Run the mature surface shutdown chain."""
        return bool(self.widget.close())


__all__ = ["ComposedFeatureSurface", "LegacyFeatureSurface"]
