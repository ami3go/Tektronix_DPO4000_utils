from __future__ import annotations

import pytest

from dpo4000_utils.automation import (
    AutomationState,
    TriggerImageConfig,
    TriggerImageController,
    trigger_acquisition_complete,
)
from dpo4000_utils.automation import triggered
from dpo4000_utils.automation.triggered import wait_for_fresh_single


class _NeverCancel:
    def is_set(self) -> bool:
        return False

    def wait(self, _timeout: float) -> bool:
        return False


class _StateScope:
    def __init__(self, active: list[bool], trigger: list[str]) -> None:
        self.active = list(active)
        self.trigger = list(trigger)
        self.calls: list[str] = []

    def get_acquisition_state(self) -> bool:
        self.calls.append("acq")
        return self.active.pop(0) if len(self.active) > 1 else self.active[0]

    def get_trigger_state(self) -> str:
        self.calls.append("trigger")
        return self.trigger.pop(0) if len(self.trigger) > 1 else self.trigger[0]

    def single_acquisition(self) -> None:
        self.calls.append("single")

    def stop_acquisition(self) -> None:
        self.calls.append("stop")


def test_trigger_config_poll_interval_and_timeout_validation() -> None:
    assert TriggerImageConfig().poll_interval_s == 0.5
    assert TriggerImageConfig().timeout_s == 30.0
    assert TriggerImageConfig(0.1, timeout_s=1.0).poll_interval_s == 0.1
    with pytest.raises(ValueError):
        TriggerImageConfig(0.05)
    with pytest.raises(ValueError):
        TriggerImageConfig(float("nan"))
    with pytest.raises(ValueError):
        TriggerImageConfig(timeout_s=0.5)
    with pytest.raises(ValueError):
        TriggerImageConfig(timeout_s=float("inf"))


def test_trigger_completion_requires_stopped_and_save() -> None:
    assert trigger_acquisition_complete(acquisition_active=False, trigger_state="SAVE")
    assert not trigger_acquisition_complete(acquisition_active=True, trigger_state="SAVE")
    assert not trigger_acquisition_complete(acquisition_active=False, trigger_state="READY")
    assert not trigger_acquisition_complete(acquisition_active=False, trigger_state="TRIGGER")


def test_fresh_single_requires_active_or_armed_state_before_save() -> None:
    scope = _StateScope(
        active=[False, True, False],
        trigger=["SAVE", "READY", "SAVE"],
    )
    result = wait_for_fresh_single(
        scope,
        _NeverCancel(),
        poll_interval_s=0.1,
        timeout_s=1.0,
    )
    assert result.completed is True
    assert result.observed_fresh_state is True
    assert result.timed_out is False
    assert scope.calls == ["acq", "trigger", "single", "acq", "trigger", "acq", "trigger"]


def test_stale_save_never_counts_as_new_single(monkeypatch) -> None:
    scope = _StateScope(active=[False], trigger=["SAVE"])
    clock = iter([0.0, 0.0, 0.6, 1.1, 1.2])
    monkeypatch.setattr(triggered.time, "monotonic", lambda: next(clock, 1.2))

    result = wait_for_fresh_single(
        scope,
        _NeverCancel(),
        poll_interval_s=0.1,
        timeout_s=1.0,
    )
    assert result.completed is False
    assert result.timed_out is True
    assert result.observed_fresh_state is False
    assert scope.calls[-1] == "stop"


def test_trigger_controller_cycle_and_rearm_state() -> None:
    controller = TriggerImageController()
    controller.start(TriggerImageConfig(rearm=True))
    assert controller.state is AutomationState.RUNNING

    token = controller.begin_cycle()
    assert token is not None
    assert controller.begin_cycle() is None
    assert controller.statistics.skipped == 1

    assert controller.finish_cycle(token, success=True)
    assert controller.statistics.succeeded == 1
    assert controller.state is AutomationState.RUNNING

    token2 = controller.begin_cycle()
    assert token2 is not None
    assert token2.sequence == 2
    assert controller.cancel_cycle(token2)


def test_trigger_controller_pause_resume_and_stale_stop() -> None:
    controller = TriggerImageController()
    controller.start(TriggerImageConfig())
    token = controller.begin_cycle()
    assert token is not None

    controller.pause()
    assert controller.state is AutomationState.PAUSED
    controller.resume()
    assert controller.state is AutomationState.RUNNING
    controller.stop()
    assert controller.state is AutomationState.IDLE
    assert controller.finish_cycle(token, success=True) is False
