"""Reviewed A2 trigger-automation behavior."""

from __future__ import annotations

from threading import Event

from PySide6.QtCore import QTimer

from ..automation import AutomationState, PeriodicImageConfig, TriggerImageConfig, TriggerWaitResult
from .automation_trigger_window import (
    PERIODIC_IMAGE_MODE,
    QtScopeWindow as AutomationA2QtScopeWindow,
)


class QtScopeWindow(AutomationA2QtScopeWindow):
    """A2 window with reviewed state ownership and recipe presentation."""

    def _automation_update_recipe(self, *_args) -> None:
        label = getattr(self, "automation_recipe_label", None)
        if label is None:
            return
        if self._automation_mode() == PERIODIC_IMAGE_MODE:
            try:
                config = PeriodicImageConfig(self._automation_interval_seconds())
            except Exception as exc:  # noqa: BLE001 - inline configuration diagnostic.
                label.setText(f"Invalid configuration: {exc}")
                return
            label.setText(
                f"Every {config.interval_s:g} seconds, save one PNG image using the File-page naming settings."
            )
            return

        try:
            config = TriggerImageConfig(
                poll_interval_s=float(self.automation_trigger_poll.value()),
                rearm=self.automation_trigger_rearm.isChecked(),
            )
        except Exception as exc:  # noqa: BLE001 - inline configuration diagnostic.
            label.setText(f"Invalid configuration: {exc}")
            return
        rearm = "then re-arm Single" if config.rearm else "then stop"
        label.setText(
            "Arm a Single acquisition, wait until that acquisition is saved and no longer running, "
            f"save one PNG, {rearm}. Poll interval {config.poll_interval_s:g} s."
        )

    def _automation_refresh_status(self) -> None:
        super()._automation_refresh_status()
        mode_combo = getattr(self, "automation_mode_combo", None)
        if mode_combo is None:
            return
        periodic_active = self._automation_controller.state in {
            AutomationState.RUNNING,
            AutomationState.PAUSED,
        }
        trigger_active = self._trigger_controller.state in {
            AutomationState.RUNNING,
            AutomationState.PAUSED,
        }
        mode_combo.setEnabled(not periodic_active and not trigger_active)

    def _trigger_cycle(self) -> None:
        """Run one reviewed arm/wait/save cycle using only public controller state."""
        trigger = self._trigger_controller
        if trigger.state is not AutomationState.RUNNING:
            return
        config = trigger.config
        if config is None:
            trigger.stop()
            self._automation_refresh_status()
            return
        token = trigger.begin_cycle()
        if token is None:
            self._automation_refresh_status()
            return

        cancel = Event()
        self._trigger_cancel_event = cancel
        self._trigger_last_state = "ARMED"
        self._automation_refresh_status()

        result = self._run_action(
            f"Waiting for triggered acquisition #{token.sequence:04d}",
            lambda scope: self._wait_for_triggered_single(
                scope,
                cancel,
                poll_interval_s=config.poll_interval_s,
            ),
        )
        self._trigger_cancel_event = None

        if token.generation != trigger.generation:
            return
        if trigger.state is not AutomationState.RUNNING:
            trigger.cancel_cycle(token)
            self._automation_refresh_status()
            return
        if not isinstance(result, TriggerWaitResult):
            trigger.finish_cycle(token, success=False, error="Could not read acquisition completion state")
            trigger.stop()
            self._automation_refresh_status()
            return

        self._trigger_last_state = result.trigger_state or self._trigger_last_state
        if result.cancelled:
            trigger.cancel_cycle(token)
            self._automation_refresh_status()
            return
        if not result.completed:
            trigger.finish_cycle(token, success=False, error="Single acquisition did not complete")
            trigger.stop()
            self._automation_refresh_status()
            return

        self._save_triggered_image(token)
        if trigger.state is not AutomationState.RUNNING:
            self._automation_refresh_status()
            return
        if config.rearm:
            QTimer.singleShot(0, self._trigger_cycle)
        else:
            trigger.stop()
            self._automation_refresh_status()


__all__ = ["QtScopeWindow"]
