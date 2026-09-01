from __future__ import annotations

from pathlib import Path

import pytest

from dpo4000_utils.automation import (
    ArtifactAction,
    BurstConfig,
    PeriodicImageConfig,
    PeriodicImageController,
    run_burst_event,
)
from dpo4000_utils.errors import DPOTransportError


class _Cancel:
    def __init__(self, *, cancel_on_wait: bool = False) -> None:
        self.cancel_on_wait = cancel_on_wait
        self.wait_calls = 0

    def is_set(self) -> bool:
        return False

    def wait(self, timeout: float) -> bool:
        self.wait_calls += 1
        return self.cancel_on_wait


class _FakeScope:
    def __init__(self, *, active_states=None, trigger_states=None, image_error=None) -> None:
        self.active_states = list(active_states or [False])
        self.trigger_states = list(trigger_states or ["SAVE"])
        self.image_error = image_error
        self.calls: list[str] = []

    def single_acquisition(self) -> None:
        self.calls.append("single")

    def stop_acquisition(self) -> None:
        self.calls.append("stop")

    def get_acquisition_state(self) -> bool:
        self.calls.append("acq_state")
        return bool(self.active_states.pop(0))

    def get_trigger_state(self) -> str:
        self.calls.append("trigger_state")
        return str(self.trigger_states.pop(0))

    def save_image_path(self, path: Path) -> Path:
        self.calls.append("image")
        if self.image_error is not None:
            raise self.image_error
        return Path(path)

    def get_record_length(self) -> int:
        self.calls.append("record_length")
        return 1000

    def save_all_channels_to_single_csv(self, path: Path, *, point_count: int) -> Path:
        self.calls.append(f"csv:{point_count}")
        return Path(path)


def test_a7_config_validates_count_delay_action_and_single_poll() -> None:
    config = BurstConfig(10, 0.0, ArtifactAction.IMAGE_CSV, single_acquisition=True)
    assert config.count == 10
    assert config.delay_s == 0.0
    assert config.action is ArtifactAction.IMAGE_CSV
    assert config.single_acquisition is True

    with pytest.raises(ValueError, match="positive integer"):
        BurstConfig(0, 1.0)
    with pytest.raises(ValueError, match="non-negative"):
        BurstConfig(1, -0.1)
    with pytest.raises(ValueError, match="Unsupported"):
        BurstConfig(1, 1.0, "binary")
    with pytest.raises(ValueError, match="Poll interval"):
        BurstConfig(1, 1.0, poll_interval_s=0.01)


def test_a7_direct_image_event_uses_public_artifact_api(tmp_path: Path) -> None:
    scope = _FakeScope()
    result = run_burst_event(
        scope,
        _Cancel(),
        BurstConfig(3, 1.0, ArtifactAction.IMAGE),
        image_path=tmp_path / "burst.png",
    )
    assert result.success is True
    assert scope.calls == ["image"]


def test_a7_direct_image_csv_event_preserves_artifact_order(tmp_path: Path) -> None:
    scope = _FakeScope()
    result = run_burst_event(
        scope,
        _Cancel(),
        BurstConfig(2, 1.0, ArtifactAction.IMAGE_CSV),
        image_path=tmp_path / "burst.png",
        csv_path=tmp_path / "burst.csv",
    )
    assert result.success is True
    assert scope.calls == ["image", "record_length", "csv:1000"]


def test_a7_single_waits_for_completed_acquisition_before_artifacts(tmp_path: Path) -> None:
    scope = _FakeScope(
        active_states=[True, False],
        trigger_states=["READY", "SAVE"],
    )
    result = run_burst_event(
        scope,
        _Cancel(),
        BurstConfig(2, 1.0, ArtifactAction.CSV, single_acquisition=True),
        csv_path=tmp_path / "burst.csv",
    )
    assert result.success is True
    assert scope.calls == [
        "single",
        "acq_state",
        "trigger_state",
        "acq_state",
        "trigger_state",
        "record_length",
        "csv:1000",
    ]


def test_a7_pause_stop_cancellation_while_waiting_single_saves_no_artifact(tmp_path: Path) -> None:
    scope = _FakeScope(active_states=[True], trigger_states=["READY"])
    cancel = _Cancel(cancel_on_wait=True)
    result = run_burst_event(
        scope,
        cancel,
        BurstConfig(2, 1.0, ArtifactAction.IMAGE, single_acquisition=True),
        image_path=tmp_path / "burst.png",
    )
    assert result.cancelled is True
    assert result.success is False
    assert "stop" in scope.calls
    assert "image" not in scope.calls


def test_a7_transport_failure_propagates(tmp_path: Path) -> None:
    scope = _FakeScope(image_error=DPOTransportError("lost session"))
    with pytest.raises(DPOTransportError):
        run_burst_event(
            scope,
            _Cancel(),
            BurstConfig(1, 1.0, ArtifactAction.IMAGE),
            image_path=tmp_path / "burst.png",
        )


def test_a7_success_count_semantics_have_no_off_by_one() -> None:
    controller = PeriodicImageController()
    controller.start(PeriodicImageConfig(1.0))
    target = 3
    for expected in range(1, target + 1):
        token = controller.begin_event()
        assert token is not None
        assert controller.finish_event(token, success=True)
        assert controller.statistics.succeeded == expected
    assert controller.statistics.succeeded == target
    assert controller.statistics.attempted == target


def test_a7_gui_uses_existing_controller_and_timer_without_gui_loop() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "dpo4000_utils" / "gui_qt" / "automation_burst_window.py"
    ).read_text(encoding="utf-8")
    assert "run_burst_event(" in source
    assert "self._automation_controller" in source
    assert "self._automation_timer" in source
    assert "token.generation != controller.generation" in source
    assert "statistics.succeeded >= config.count" in source
    assert "while True" not in source
    assert ".query(" not in source
    assert ".write(" not in source
    assert "CURVE?" not in source
