from __future__ import annotations

from array import array

from dpo4000_utils.logger.dpo4log import (
    Dpo4LogWriter,
    iter_dpo4log_records,
    scan_dpo4log,
)
from dpo4000_utils.logger.log_cli import main as log_cli_main
from dpo4000_utils.logger.models import LoggerRecord, WaveformSnapshot


def _record(sequence: int) -> LoggerRecord:
    snapshot = WaveformSnapshot(
        source="CH1",
        label="CH1",
        start_index=1,
        stop_index=3,
        acquired_utc="2026-09-01T00:00:00+00:00",
        typecode="h",
        sample_bytes=array("h", [1, -2, 300]).tobytes(),
        sample_count=3,
        byte_order="little",
        preamble={
            "byte_width": 2,
            "encoding": "BINARY",
            "binary_format": "RI",
            "byte_order": "MSB",
            "record_point_count": 3,
            "point_format": "Y",
            "x_unit": "s",
            "x_increment": 1e-6,
            "x_zero": 0.0,
            "point_offset": 0.0,
            "y_unit": "V",
            "y_multiplier": 0.01,
            "y_offset": 0.0,
            "y_zero": 0.0,
        },
    )
    return LoggerRecord(sequence=sequence, captured_utc=f"t{sequence}", waveforms=(snapshot,))


def test_dpo4log_scan_is_bounded_by_default_and_can_explicitly_load_records(tmp_path) -> None:
    path = tmp_path / "run.dpo4log"
    writer = Dpo4LogWriter(path, run_metadata={"scope": "fake"})
    writer.append(_record(1))
    writer.append(_record(2))
    writer.close()

    bounded = scan_dpo4log(path)
    assert bounded.records == ()
    assert bounded.record_count == 2
    assert bounded.clean_end
    assert not bounded.truncated

    loaded = scan_dpo4log(path, load_records=True)
    assert [record.sequence for record in loaded.records] == [1, 2]
    assert loaded.records[0].waveforms[0].samples().tolist() == [1, -2, 300]
    assert [record.sequence for record in iter_dpo4log_records(path)] == [1, 2]


def test_dpo4log_recovers_complete_records_before_incomplete_final_frame(tmp_path) -> None:
    path = tmp_path / "run.dpo4log"
    writer = Dpo4LogWriter(path)
    writer.append(_record(1))
    writer._handle.flush()  # noqa: SLF001 - deliberate corruption test.
    writer._handle.close()  # noqa: SLF001
    writer._closed = True  # noqa: SLF001
    with path.open("ab") as handle:
        handle.write(b"FRM1\x01")
    result = scan_dpo4log(path)
    assert result.truncated
    assert not result.clean_end
    assert result.record_count == 1
    assert [record.sequence for record in iter_dpo4log_records(path, strict=False)] == [1]


def test_dpo4log_cli_inspect_and_stream_convert(tmp_path) -> None:
    source = tmp_path / "run.dpo4log"
    destination = tmp_path / "run.csv"
    writer = Dpo4LogWriter(source, run_metadata={"scope": "fake"})
    writer.append(_record(1))
    writer.close()

    assert log_cli_main(["inspect", str(source), "--json"]) == 0
    assert log_cli_main(["convert", str(source), "--csv", str(destination)]) == 0
    text = destination.read_text(encoding="utf-8")
    assert "RECORD_BEGIN" in text
    assert "RECORD_END" in text
