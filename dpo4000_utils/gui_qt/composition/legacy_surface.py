"""Compatibility adapter for the mature v0.7 feature surface.

The v0.8 production window never inherits from the historical window stack. The
old stack is instantiated behind this one adapter while individual pages and
cross-cutting responsibilities are migrated into composition controllers. This
module is intentionally the only composition module allowed to import a legacy
``*_window`` implementation.
"""

from __future__ import annotations

from pathlib import Path
import time
from typing import Any

from PySide6.QtWidgets import QBoxLayout, QCheckBox, QFormLayout

from ...settings import save_scope_settings_file
from ..milestone_a_window import QtScopeWindow as MilestoneAFeatureWindow
from .pages.live_waveform import attach_live_waveform_panel
from .pages import (
    attach_measurement_trend_panel,
    attach_scientific_export_panel,
    build_connection_page,
    build_recipe_page,
    build_trigger_page,
)


AUTOMATION_PREVIEW_MIN_INTERVAL_S = 0.5


def automation_settings_path(artifact: Path) -> Path:
    """Settings JSON path sharing an automation event's artifact stem."""
    return artifact.with_name(f"{artifact.stem}.settings.json")


class ComposedFeatureSurface(MilestoneAFeatureWindow):
    """Compatibility surface whose migrated pages are owned by composition."""

    # Every legacy Automation mode records each saved event artifact in
    # ``_automation_last_path`` (manual File-page captures never do). Intercepting
    # that one attribute adds post-capture preview refresh and per-event settings
    # JSON for all modes without touching the individual legacy mode classes.
    @property
    def _automation_last_path(self) -> Path | None:
        return self.__dict__.get("_composed_automation_last_path")

    @_automation_last_path.setter
    def _automation_last_path(self, value: Path | None) -> None:
        self.__dict__["_composed_automation_last_path"] = value
        if value is None:
            return
        artifact = Path(value)
        if artifact.suffix.lower() == ".png":
            self._automation_refresh_preview(artifact)
        self._automation_save_settings(artifact)

    def _automation_option(self, name: str, default: bool) -> bool:
        box = self.__dict__.get(name)
        if box is None:
            return default
        try:
            return bool(box.isChecked())
        except RuntimeError:
            # The option widget was destroyed (page rebuilt); never fail an event for it.
            return default

    def _automation_refresh_preview(self, image: Path) -> None:
        if not self._automation_option("automation_preview_refresh_check", True):
            return
        if getattr(self, "preview_label", None) is None or not hasattr(self, "_load_preview"):
            return
        now = time.monotonic()
        # Throttle so fast Burst/Periodic runs cannot stall the GUI thread with decodes.
        if now - self.__dict__.get("_automation_preview_refreshed_at", float("-inf")) < AUTOMATION_PREVIEW_MIN_INTERVAL_S:
            return
        self.__dict__["_automation_preview_refreshed_at"] = now
        self._load_preview(image)

    def _automation_save_settings(self, artifact: Path) -> None:
        if not self._automation_option("automation_settings_json_check", False):
            return
        target = automation_settings_path(artifact)
        # Image + CSV events report two artifacts with one stem; save once per event.
        if self.__dict__.get("_automation_settings_last_target") == target:
            return
        self.__dict__["_automation_settings_last_target"] = target

        def execute(scope: Any) -> Path:
            return save_scope_settings_file(scope, target, settings_folder=target.parent)

        def finished(result: Any) -> None:
            log = getattr(self, "_append_log", None)
            if log is not None:
                log(f"Saved automation scope settings: {result}")

        def failed(exc: BaseException) -> None:
            log = getattr(self, "_append_log", None)
            if log is not None:
                log(f"Automation scope settings not saved for {artifact.name}: {exc}")

        self._run_action(
            "Saving automation scope settings",
            execute,
            on_success=finished,
            on_error=failed,
            retain_session=True,
        )

    def _build_automation_output_card(self):
        """Add post-capture preview refresh and per-event settings JSON options."""
        card = super()._build_automation_output_card()
        self.automation_preview_refresh_check = QCheckBox("Refresh preview after each automation PNG")
        self.automation_preview_refresh_check.setObjectName("automationPreviewRefreshCheck")
        self.automation_preview_refresh_check.setChecked(True)
        self.automation_settings_json_check = QCheckBox("Also save scope settings JSON per event")
        self.automation_settings_json_check.setObjectName("automationSettingsJsonCheck")
        self.automation_settings_json_check.setToolTip(
            "Read-only *LRN? setup saved as <event>.settings.json next to the event's PNG/CSV"
        )
        layout = card.layout()
        for box in (self.automation_preview_refresh_check, self.automation_settings_json_check):
            if isinstance(layout, QFormLayout):
                layout.addRow(box)
            elif isinstance(layout, QBoxLayout):
                layout.addWidget(box)
        return card

    def _run_action(
        self, description, callback, *, on_success=None, on_error=None,
        retain_session: bool = False,
    ):
        # Centralized instrument lease: A22 permits only its own worker reads.
        # Local pure-data operations do not call this gateway and remain available.
        if getattr(self, "_composition_live_lease", False) and not str(
            description
        ).startswith("A22 live waveform snapshot"):
            error = RuntimeError("A22 owns the instrument; Stop live streaming first")
            self.statusBar().showMessage(str(error))
            if on_error is not None:
                on_error(error)
            return None
        return super()._run_action(
            description, callback, on_success=on_success,
            on_error=on_error, retain_session=retain_session,
        )

    def closeEvent(self, event):  # noqa: N802 - Qt convention.
        panel = getattr(self, "_composition_live_stream_panel", None)
        if panel is not None:
            panel.shutdown()  # Stop scheduling before serialized session shutdown.
        super().closeEvent(event)

    def _build_connection_tab(self):
        """Use the native composed Connection page in the production surface."""
        return build_connection_page(self)

    def _build_measurement_tab(self):
        """Preserve measurement management and attach the composed A20 dashboard."""
        page = super()._build_measurement_tab()
        return attach_live_waveform_panel(self, attach_measurement_trend_panel(self, page))

    def _build_trigger_tab(self):
        """Use the native composed A14 Advanced Trigger page."""
        return build_trigger_page(self)

    def _build_recipe_tab(self):
        """Use the native composed A15/A16 Recipe + Rules page."""
        return build_recipe_page(self)

    def _build_file_tab(self):
        """Preserve the mature File page and attach the composed A21 exporter."""
        page = super()._build_file_tab()
        return attach_scientific_export_panel(self, page)

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
