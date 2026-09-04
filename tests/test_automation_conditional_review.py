from __future__ import annotations

from pathlib import Path

from dpo4000_utils.automation import (
    ArtifactAction,
    PeriodicImageConfig,
    PeriodicImageController,
    capture_artifacts,
)


class _PartialScope:
    def save_image_path(self, path: Path) -> Path:
        return Path(path)

    def get_record_length(self) -> int:
        return 1000

    def save_all_channels_to_single_csv(self, path: Path, *, point_count: int) -> Path:
        raise ValueError("CSV write failed")


def test_a6_normal_skip_clears_previous_transient_error() -> None:
    controller = PeriodicImageController()
    controller.start(PeriodicImageConfig(1.0))

    first = controller.begin_event()
    assert first is not None
    controller.finish_skipped(first, reason="invalid measurement")
    assert controller.statistics.last_error == "invalid measurement"

    second = controller.begin_event()
    assert second is not None
    controller.finish_skipped(second)
    assert controller.statistics.last_error == ""


def test_a6_partial_artifact_error_names_written_image(tmp_path: Path) -> None:
    image = tmp_path / "capture.png"
    csv_path = tmp_path / "capture.csv"
    result = capture_artifacts(
        _PartialScope(),
        ArtifactAction.IMAGE_CSV,
        image_path=image,
        csv_path=csv_path,
    )
    assert result.success is False
    assert result.image_path == image
    assert "partial artifacts" in result.error
    assert str(image) in result.error


def test_a6_review_window_guards_stale_generation_and_has_no_raw_io() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "dpo4000_utils" / "gui_qt" / "automation_conditional_review_window.py"
    ).read_text(encoding="utf-8")
    assert "tracked_generation" in source
    assert "self._automation_controller.generation" in source
    assert ".query(" not in source
    assert ".write(" not in source
