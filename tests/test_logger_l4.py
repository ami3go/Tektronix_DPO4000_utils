from __future__ import annotations

from array import array

from dpo4000_utils.logger.dpo4log import Dpo4LogWriter, scan_dpo4log
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


def test_dpo4log_round_trip_preserves_raw_samples(tmp_path) -> None:
    path = tmp_path / "run.dpo4log"
    writer = Dpo4LogWriter(path, run_metadata={"scope": "fake"})
    writer.append(_record(1))
    writer.append(_record(2))
    writer.close()
    result = scan_dpo4log(path)
    assert not result.truncated
    assert result.header["scope"] == "fake"
    assert [record.sequence for record in result.records] == [1, 2]
    assert result.records[0].waveforms[0].samples().tolist() == [1, -2, 300]


def test_dpo4log_ignores_incomplete_final_frame(tmp_path) -> None:
    path = tmp_path / "run.dpo4log"
    writer = Dpo4LogWriter(path)
    writer.append(_record(1))
    # Simulate power loss before the writer can emit END_OF_RUN: keep prior complete frame,
    # then append an incomplete frame prefix fragment.
    writer._handle.flush()  # noqa: SLF001 - deliberate corruption test.
    writer._handle.close()  # noqa: SLF001
    writer._closed = True  # noqa: SLF001
    with path.open("ab") as handle:
        handle.write(b"FRM1\x01")
    result = scan_dpo4log(path)
    assert result.truncated
    assert [record.sequence for record in result.records] == [1]
