from __future__ import annotations

from pathlib import Path

from dpo4000_utils.automation.waveform_logging import save_full_record_csv


class _FakeScope:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls: list[object] = []
        self.error = error

    def get_record_length(self) -> int:
        self.calls.append("record_length")
        return 1_000_000

    def save_all_channels_to_single_csv(self, path: Path, **options) -> Path:
        self.calls.append(("csv", Path(path), dict(options)))
        if self.error is not None:
            raise self.error
        return Path(path)


def test_a4_uses_current_full_record_length(tmp_path: Path) -> None:
    scope = _FakeScope()
    target = tmp_path / "waveform.csv"

    result = save_full_record_csv(scope, target)

    assert result.success is True
    assert result.csv_path == target
    assert result.point_count == 1_000_000
    assert scope.calls == [
        "record_length",
        ("csv", target, {"point_count": 1_000_000}),
    ]


def test_a4_non_transport_output_failure_is_structured(tmp_path: Path) -> None:
    scope = _FakeScope(error=OSError("disk full"))

    result = save_full_record_csv(scope, tmp_path / "waveform.csv")

    assert result.success is False
    assert result.csv_path is None
    assert result.point_count == 1_000_000
    assert "disk full" in result.error


def test_a4_gui_has_no_image_capture_or_raw_scope_protocol() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "dpo4000_utils" / "gui_qt" / "automation_waveform_window.py").read_text(
        encoding="utf-8"
    )

    assert "save_full_record_csv(" in source
    assert "save_image_path" not in source
    assert ".query(" not in source
    assert ".write(" not in source
    assert "CURVE?" not in source
