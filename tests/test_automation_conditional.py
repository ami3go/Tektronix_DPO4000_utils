from __future__ import annotations

from pathlib import Path

import pytest

from dpo4000_utils.automation import (
    ArtifactAction,
    ConditionalCaptureConfig,
    ConditionalEvaluator,
    PeriodicImageConfig,
    PeriodicImageController,
    capture_artifacts,
    parse_measurement_value,
    run_conditional_poll,
)
from dpo4000_utils.errors import DPOTransportError


class _FakeScope:
    def __init__(self, values=None, *, measurement_error=None, csv_error=None) -> None:
        self.values = list(values or ["0"])
        self.measurement_error = measurement_error
        self.csv_error = csv_error
        self.calls: list[str] = []

    def read_measurement_value(self, slot: int) -> str:
        self.calls.append(f"measure:{slot}")
        if self.measurement_error is not None:
            raise self.measurement_error
        return str(self.values.pop(0))

    def save_image_path(self, path: Path) -> Path:
        self.calls.append("image")
        return Path(path)

    def get_record_length(self) -> int:
        self.calls.append("record_length")
        return 1000

    def save_all_channels_to_single_csv(self, path: Path, *, point_count: int) -> Path:
        self.calls.append(f"csv:{point_count}")
        if self.csv_error is not None:
            raise self.csv_error
        return Path(path)


def test_a6_config_validates_range_delta_and_cooldown() -> None:
    config = ConditionalCaptureConfig(1, "inside", 1.0, high=2.0, consecutive_matches=3)
    assert config.slot == 1
    assert config.operator == "inside"

    with pytest.raises(ValueError, match="both low and high"):
        ConditionalCaptureConfig(1, "inside", 1.0)
    with pytest.raises(ValueError, match="must not exceed"):
        ConditionalCaptureConfig(1, "outside", 3.0, high=2.0)
    with pytest.raises(ValueError, match="non-negative"):
        ConditionalCaptureConfig(1, "abs_delta", -1.0)
    with pytest.raises(ValueError, match="at least 1 second"):
        ConditionalCaptureConfig(1, ">", 1.0, cooldown_s=0.0)


def test_a6_debounce_resets_when_condition_becomes_false() -> None:
    evaluator = ConditionalEvaluator(
        ConditionalCaptureConfig(1, ">", 10.0, consecutive_matches=3, cooldown_s=10.0)
    )
    assert evaluator.evaluate("11", now_s=0.0).fire is False
    assert evaluator.evaluate("12", now_s=1.0).streak == 2
    reset = evaluator.evaluate("9", now_s=2.0)
    assert reset.matched is False
    assert reset.streak == 0
    assert evaluator.evaluate("11", now_s=3.0).fire is False
    assert evaluator.evaluate("12", now_s=4.0).fire is False
    assert evaluator.evaluate("13", now_s=5.0).fire is True


def test_a6_invalid_value_resets_debounce_and_does_not_match() -> None:
    evaluator = ConditionalEvaluator(
        ConditionalCaptureConfig(1, ">=", 1.0, consecutive_matches=2, cooldown_s=5.0)
    )
    assert evaluator.evaluate("2", now_s=0.0).streak == 1
    invalid = evaluator.evaluate("9.9E37", now_s=1.0)
    assert invalid.valid is False
    assert invalid.matched is False
    assert evaluator.streak == 0
    assert evaluator.previous_value is None
    assert evaluator.evaluate("2", now_s=2.0).fire is False


def test_a6_cooldown_prevents_persistent_condition_from_flooding() -> None:
    evaluator = ConditionalEvaluator(
        ConditionalCaptureConfig(1, ">", 0.0, consecutive_matches=1, cooldown_s=10.0)
    )
    assert evaluator.evaluate("1", now_s=0.0).fire is True
    blocked = evaluator.evaluate("1", now_s=1.0)
    assert blocked.fire is False
    assert blocked.cooldown_remaining_s == pytest.approx(9.0)
    assert evaluator.evaluate("1", now_s=10.0).fire is True


def test_a6_absolute_delta_uses_previous_valid_sample() -> None:
    evaluator = ConditionalEvaluator(
        ConditionalCaptureConfig(1, "abs_delta", 2.0, cooldown_s=5.0)
    )
    first = evaluator.evaluate("10", now_s=0.0)
    assert first.matched is False
    second = evaluator.evaluate("13", now_s=1.0)
    assert second.fire is True
    assert second.previous_value == pytest.approx(10.0)


def test_a6_parse_measurement_accepts_prefixed_response_and_rejects_sentinel() -> None:
    assert parse_measurement_value("MEASUREMENT:MEAS1:VALUE 1.25") == pytest.approx(1.25)
    with pytest.raises(ValueError, match="invalid"):
        parse_measurement_value("9.9E37")


def test_a6_poll_does_not_capture_until_condition_fires(tmp_path: Path) -> None:
    scope = _FakeScope(["4", "6"])
    evaluator = ConditionalEvaluator(
        ConditionalCaptureConfig(2, ">", 5.0, cooldown_s=10.0)
    )
    first = run_conditional_poll(
        scope,
        evaluator,
        now_s=0.0,
        action=ArtifactAction.IMAGE,
        image_path=str(tmp_path / "one.png"),
    )
    assert first.captured is False
    assert scope.calls == ["measure:2"]

    second = run_conditional_poll(
        scope,
        evaluator,
        now_s=1.0,
        action=ArtifactAction.IMAGE,
        image_path=str(tmp_path / "two.png"),
    )
    assert second.captured is True
    assert scope.calls[-2:] == ["measure:2", "image"]


def test_a6_image_csv_reports_partial_non_transport_failure(tmp_path: Path) -> None:
    scope = _FakeScope(csv_error=ValueError("disk conversion failed"))
    result = capture_artifacts(
        scope,
        ArtifactAction.IMAGE_CSV,
        image_path=tmp_path / "capture.png",
        csv_path=tmp_path / "capture.csv",
    )
    assert result.success is False
    assert result.image_path == tmp_path / "capture.png"
    assert result.csv_path is None
    assert "disk conversion failed" in result.error


def test_a6_transport_failure_propagates(tmp_path: Path) -> None:
    scope = _FakeScope(measurement_error=DPOTransportError("lost session"))
    evaluator = ConditionalEvaluator(ConditionalCaptureConfig(1, ">", 0.0))
    with pytest.raises(DPOTransportError):
        run_conditional_poll(
            scope,
            evaluator,
            now_s=0.0,
            action=ArtifactAction.CSV,
            csv_path=str(tmp_path / "capture.csv"),
        )


def test_periodic_controller_can_finish_reserved_event_as_skipped() -> None:
    controller = PeriodicImageController()
    controller.start(PeriodicImageConfig(1.0))
    token = controller.begin_event()
    assert token is not None
    assert controller.finish_skipped(token) is True
    assert controller.busy is False
    assert controller.statistics.attempted == 1
    assert controller.statistics.skipped == 1
    assert controller.statistics.succeeded == 0
    assert controller.statistics.failed == 0
