from pathlib import Path

import pytest

from dpo4000_utils.automation import (
    AutomationState,
    PeriodicImageConfig,
    PeriodicImageController,
    append_sequence,
    collision_safe_path,
)


def test_periodic_image_config_validates_interval() -> None:
    assert PeriodicImageConfig(1).interval_s == 1.0
    assert PeriodicImageConfig(60).interval_s == 60.0
    with pytest.raises(ValueError):
        PeriodicImageConfig(0.5)
    with pytest.raises(ValueError):
        PeriodicImageConfig(float("inf"))


def test_controller_start_pause_resume_stop() -> None:
    controller = PeriodicImageController()
    controller.start(PeriodicImageConfig(5))
    assert controller.state is AutomationState.RUNNING

    controller.pause()
    assert controller.state is AutomationState.PAUSED
    assert controller.begin_event() is None

    controller.resume()
    assert controller.state is AutomationState.RUNNING
    controller.stop()
    assert controller.state is AutomationState.IDLE
    assert controller.config is None


def test_controller_rejects_overlap_and_counts_skip() -> None:
    controller = PeriodicImageController()
    controller.start(PeriodicImageConfig(1))

    token = controller.begin_event()
    assert token is not None
    assert controller.busy
    assert controller.begin_event() is None
    assert controller.statistics.skipped == 1

    assert controller.finish_event(token, success=True)
    assert not controller.busy
    assert controller.statistics.attempted == 1
    assert controller.statistics.succeeded == 1


def test_stale_completion_is_ignored_after_stop() -> None:
    controller = PeriodicImageController()
    controller.start(PeriodicImageConfig(1))
    token = controller.begin_event()
    assert token is not None

    controller.stop()
    assert controller.finish_event(token, success=True) is False
    assert controller.state is AutomationState.IDLE


def test_force_event_supports_run_once_while_idle() -> None:
    controller = PeriodicImageController()
    assert controller.begin_event() is None
    token = controller.begin_event(force=True)
    assert token is not None
    assert token.sequence == 1
    assert controller.finish_event(token, success=False, error="test")
    assert controller.statistics.failed == 1
    assert controller.statistics.last_error == "test"


def test_sequence_and_collision_safe_path(tmp_path: Path) -> None:
    base = tmp_path / "scope_screen.png"
    sequenced = append_sequence(base, 3)
    assert sequenced.name == "scope_screen_0003.png"
    assert collision_safe_path(sequenced) == sequenced

    sequenced.write_bytes(b"old")
    alternate = collision_safe_path(sequenced)
    assert alternate.name == "scope_screen_0003_001.png"
    assert not alternate.exists()
