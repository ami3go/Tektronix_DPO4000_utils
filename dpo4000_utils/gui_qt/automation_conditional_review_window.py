"""Reviewed A6 Conditional Capture UI behavior."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..automation import AutomationState
from .automation_conditional_window import QtScopeWindow as AutomationA6QtScopeWindow


class QtScopeWindow(AutomationA6QtScopeWindow):
    """A6 window that ignores worker completions belonging to a stopped run."""

    def __init__(self, *args, **kwargs) -> None:
        self._discarded_conditional_completion = False
        super().__init__(*args, **kwargs)

    def _run_action(
        self,
        description: str,
        callback: Callable[[Any], object],
        *,
        on_success: Callable[[object], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
        retain_session: bool = False,
    ) -> None:
        tracked_generation = None
        if str(description).startswith("Evaluating conditional capture #"):
            tracked_generation = self._automation_controller.generation

        def stale_completion() -> bool:
            if tracked_generation is None:
                return False
            if tracked_generation == self._automation_controller.generation:
                return False
            self._discarded_conditional_completion = True
            return True

        def completed(value: object) -> None:
            if stale_completion():
                return
            if on_success is not None:
                on_success(value)

        def failed(exc: BaseException) -> None:
            if stale_completion():
                return
            if on_error is not None:
                on_error(exc)

        super()._run_action(
            description,
            callback,
            on_success=completed,
            on_error=failed,
            retain_session=retain_session,
        )

    def stop_automation(self) -> None:
        if (
            self._discarded_conditional_completion
            and self._automation_controller.state is AutomationState.IDLE
        ):
            self._discarded_conditional_completion = False
            self._automation_refresh_status()
            return
        self._discarded_conditional_completion = False
        super().stop_automation()


__all__ = ["QtScopeWindow"]
