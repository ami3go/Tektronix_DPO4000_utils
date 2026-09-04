"""Reviewed A9 retention authorization and startup behavior."""

from __future__ import annotations

from pathlib import Path

from .automation_retention_window import QtScopeWindow as AutomationA9QtScopeWindow


class QtScopeWindow(AutomationA9QtScopeWindow):
    """A9 window with preview authorization bound to one resolved output root."""

    def __init__(self, *args, **kwargs) -> None:
        self._retention_preview_root: Path | None = None
        super().__init__(*args, **kwargs)

    def _retention_policy_changed(self, *_args) -> None:
        self._retention_preview_root = None
        super()._retention_policy_changed(*_args)

    def preview_retention_policy(self) -> None:
        super().preview_retention_policy()
        if self._retention_preview_ack:
            try:
                self._retention_preview_root = self._current_retention_root()
            except Exception:
                self._retention_preview_root = None
                self._retention_preview_ack = False
                self.automation_retention_auto.setChecked(False)
                self.automation_retention_auto.setEnabled(False)

    def _automatic_retention_authorized_for_current_root(self) -> bool:
        if not self.automation_retention_auto.isChecked():
            return True
        if not self._retention_preview_ack or self._retention_preview_root is None:
            return False
        try:
            return self._current_retention_root() == self._retention_preview_root
        except Exception:
            return False

    def _guard_retention_preview_root(self) -> bool:
        if self._automatic_retention_authorized_for_current_root():
            return True
        self.automation_retention_auto.setChecked(False)
        self.automation_retention_auto.setEnabled(False)
        self._retention_preview_ack = False
        self._retention_preview_root = None
        self.automation_retention_status.setText(
            "Output folder changed. Preview retention again before automatic deletion can be enabled."
        )
        self._message(
            "Automation",
            "Output folder changed after the retention preview. Preview retention again before starting automatic deletion.",
            error=True,
        )
        return False

    def start_automation(self) -> None:
        if not self._guard_retention_preview_root():
            return
        super().start_automation()
        if self._automation_any_active() and self.automation_retention_auto.isChecked():
            self._apply_retention_after_event()

    def run_automation_once(self) -> None:
        if not self._guard_retention_preview_root():
            return
        super().run_automation_once()


__all__ = ["QtScopeWindow"]
