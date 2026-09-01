from __future__ import annotations

from pathlib import Path

from dpo4000_utils.automation.bundle import (
    acquire_trigger_bundle,
    collision_safe_bundle_paths,
)


class _NeverCancel:
    def is_set(self) -> bool:
        return False

    def wait(self, _timeout: float) -> bool:
        return False


class _CancelImmediately:
    def is_set(self) -> bool:
        return True

    def wait(self, _timeout: float) -> bool:
        return True


class _FakeScope:
    def __init__(self, *, csv_error: Exception | None = None) -> None:
        self.calls: list[object] = []
        self.csv_error = csv_error

    def single_acquisition(self) -> None:
        self.calls.append("single")

    def stop_acquisition(self) -> None:
        self.calls.append("stop")

    def get_acquisition_state(self) -> bool:
        self.calls.append("acquisition_state")
        return False

    def get_trigger_state(self) -> str:
        self.calls.append("trigger_state")
        return "SAVE"

    def save_image_path(self, path: Path) -> Path:
        self.calls.append(("image", Path(path)))
        return Path(path)

    def get_record_length(self) -> int:
        self.calls.append("record_length")
        return 100_000

    def save_all_channels_to_single_csv(self, path: Path, **options) -> Path:
        self.calls.append(("csv", Path(path), dict(options)))
        if self.csv_error is not None:
            raise self.csv_error
        return Path(path)


def test_a3_saves_image_then_full_record_csv_before_any_rearm(tmp_path: Path) -> None:
    scope = _FakeScope()
    image = tmp_path / "capture.png"
    csv = tmp_path / "capture.csv"

    result = acquire_trigger_bundle(
        scope,
        _NeverCancel(),
        poll_interval_s=0.5,
        image_path=image,
        csv_path=csv,
    )

    assert result.completed is True
    assert result.cancelled is False
    assert result.artifacts_complete is True
    assert result.image_path == image
    assert result.csv_path == csv
    assert result.point_count == 100_000
    assert scope.calls == [
        "single",
        "acquisition_state",
        "trigger_state",
        ("image", image),
        "record_length",
        ("csv", csv, {"point_count": 100_000}),
    ]


def test_a3_cancellation_stops_acquisition_without_writing_artifacts(tmp_path: Path) -> None:
    scope = _FakeScope()

    result = acquire_trigger_bundle(
        scope,
        _CancelImmediately(),
        poll_interval_s=0.5,
        image_path=tmp_path / "capture.png",
        csv_path=tmp_path / "capture.csv",
    )

    assert result.cancelled is True
    assert result.completed is False
    assert result.artifacts_complete is False
    assert scope.calls == ["single", "stop"]


def test_a3_non_transport_csv_failure_is_structured_partial_result(tmp_path: Path) -> None:
    scope = _FakeScope(csv_error=OSError("disk full"))
    image = tmp_path / "capture.png"
    csv = tmp_path / "capture.csv"

    result = acquire_trigger_bundle(
        scope,
        _NeverCancel(),
        poll_interval_s=0.5,
        image_path=image,
        csv_path=csv,
    )

    assert result.completed is True
    assert result.artifacts_complete is False
    assert result.image_path == image
    assert result.csv_path is None
    assert "disk full" in result.error
    assert scope.calls.count("single") == 1
    assert scope.calls[-1][0] == "csv"


def test_a3_collision_suffix_is_shared_by_png_and_csv(tmp_path: Path) -> None:
    image = tmp_path / "capture_0001.png"
    csv = tmp_path / "waveform_0001.csv"
    image.write_bytes(b"old")

    safe_image, safe_csv = collision_safe_bundle_paths(image, csv)

    assert safe_image.name == "capture_0001_001.png"
    assert safe_csv.name == "waveform_0001_001.csv"


def test_a3_gui_stays_behind_public_driver_boundary() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (
        root / "dpo4000_utils" / "gui_qt" / "automation_trigger_bundle_window.py"
    ).read_text(encoding="utf-8")

    assert "acquire_trigger_bundle(" in source
    assert ".query(" not in source
    assert ".write(" not in source
    assert "ACQUIRE:" not in source
    assert "TRIGGER:" not in source
    assert "CURVE?" not in source
