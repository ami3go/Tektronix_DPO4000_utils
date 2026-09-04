from __future__ import annotations

import pytest

from dpo4000_utils.automation import (
    AutomationState,
    TriggerImageConfig,
    TriggerImageController,
    trigger_acquisition_complete,
)


def test_trigger_config_poll_interval_validation() -> None:
    assert TriggerImageConfig().poll_interval_s == 0.5
    assert TriggerImageConfig(0.1).poll_interval_s == 0.1
    with pytest.raises(ValueError):
        TriggerImageConfig(0.05)
    with pytest.raises(ValueError):
        TriggerImageConfig(float("nan"))


def test_trigger_completion_requires_stopped_and_save() -> None:
    assert trigger_acquisition_complete(acquisition_active=False, trigger_state="SAVE")
    assert not trigger_acquisition_complete(acquisition_active=True, trigger_state="SAVE")
    assert not trigger_acquisition_complete(acquisition_active=False, trigger_state="READY")
    assert not trigger_acquisition_complete(acquisition_active=False, trigger_state="TRIGGER")


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
