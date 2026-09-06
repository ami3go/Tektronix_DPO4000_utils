"""Compatibility adapter for the mature v0.7 feature surface.

The v0.8 production window never inherits from the historical window stack.  The
old stack is instantiated behind this one adapter while individual page and
cross-cutting responsibilities are migrated into composition controllers.  This
module is intentionally the only composition module allowed to import a legacy
``*_window`` implementation.
"""

from __future__ import annotations

from pathlib import Path

from ..milestone_a_window import QtScopeWindow as MilestoneAFeatureWindow


class LegacyFeatureSurface:
    """Own the mature feature widget used during the v0.8 migration boundary."""

    def __init__(self, preferences_path: str | Path | None = None) -> None:
        self.widget = MilestoneAFeatureWindow(preferences_path=preferences_path)

    def close(self) -> bool:
        """Run the mature surface shutdown chain."""
        return bool(self.widget.close())


__all__ = ["LegacyFeatureSurface"]
