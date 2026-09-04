from __future__ import annotations

from array import array
from datetime import datetime, timezone
from pathlib import Path

import pytest

from dpo4000_utils.logger import LoggerConfig, LoggerMode, WaveformSnapshot, capture_logger_record
from dpo4000_utils.waveform import WaveformData, WaveformPreamble


def _waveform(source: str = "CH1") -> WaveformData:
    return WaveformData(
        source=source,
        label=source,
        start_index=1,
        stop_index=3,
        requested_encoding="RIBINARY",
        preamble=WaveformPreamble(
            byte_width=2,
            encoding="BINARY",
            binary_format="RI",
            byte_order="MSB",
            record_point_count=3,
            point_format="Y",
            x_unit="s",
            x_increment=1e-6,
            x_zero=0.0,
            point_offset=0.0,
            y_unit="V",
            y_multiplier=0.01,
            y_offset=0.0,
            y_zero=0.0,
        ),
        samples=array("h", [1, 2, 3]),
        acquired_at=datetime.now(timezone.utc),
    )


def test_logger_config_normalizes_waveform_sources_and_rejects_empty_waveform_selection() -> None:
    config = LoggerConfig(waveform_sources=("ch1", "CH1", "2"))
    assert config.waveform_sources == ("CH1", "CH2")
    with pytest.raises(ValueError):
        LoggerConfig(mode=LoggerMode.WAVEFORM, waveform_sources=())


def test_waveform_snapshot_keeps_compact_raw_samples_and_scaling() -> None:
    snapshot = WaveformSnapshot.from_waveform(_waveform())
    assert snapshot.sample_count == 3
    assert snapshot.samples().tolist() == [1, 2, 3]
    assert snapshot.time_at(2) == pytest.approx(2e-6)
    assert snapshot.value_at(2) == pytest.approx(0.03)


def test_capture_logger_record_uses_public_read_waveform_api() -> None:
    calls: list[object] = []

    class FakeScope:
        def read_waveform(self, request):
            calls.append(request)
            return _waveform(str(request.source))

    record = capture_logger_record(
        FakeScope(),
        LoggerConfig(waveform_sources=("CH1", "CH2")),
        7,
    )
    assert record.sequence == 7
    assert [item.source for item in record.waveforms] == ["CH1", "CH2"]
    assert len(calls) == 2


def test_logger_gui_boundary_and_canonical_page_order() -> None:
    root = Path(__file__).resolve().parents[1]
    source = (root / "dpo4000_utils" / "gui_qt" / "logger_window.py").read_text(encoding="utf-8")
    layout = (root / "dpo4000_utils" / "gui_qt" / "logger_page_layout.py").read_text(encoding="utf-8")
    assert ".query(" not in source
    assert ".write(" not in source
    assert "scope.read_waveform" not in source
    assert '"Automation",\n    "Logger",\n    "File"' in layout
    assert "FILE_PAGE_INDEX = 7" in layout
