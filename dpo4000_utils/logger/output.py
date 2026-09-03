"""Logger output-session multiplexer for CSV and DPO4LOG."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from .bus_csv import BusCsvStreamWriter
from .csv_stream import WaveformCsvStreamWriter
from .dpo4log import Dpo4LogWriter
from .measurement_csv import MeasurementCsvStreamWriter
from .mixed_csv import MixedCsvStreamWriter
from .models import LoggerMode, LoggerOutputFormat, LoggerRecord

class LoggerOutputSession:
    def __init__(self, root: str | Path, output_format: LoggerOutputFormat, *, mode: LoggerMode = LoggerMode.WAVEFORM, measurement_slots: tuple[int, ...] = (), run_metadata: Mapping[str, Any] | None = None) -> None:
        self.root = Path(root).expanduser(); self.root.mkdir(parents=True, exist_ok=True)
        self.output_format = LoggerOutputFormat(output_format); self.mode = LoggerMode(mode)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ"); self.stem = f"logger_{stamp}_0000"
        self.csv_writer: Any = None; self.binary_writer: Dpo4LogWriter | None = None
        if self.output_format in {LoggerOutputFormat.CSV, LoggerOutputFormat.BOTH}:
            csv_path = self.root / f"{self.stem}.csv"
            if self.mode is LoggerMode.MEASUREMENTS: self.csv_writer = MeasurementCsvStreamWriter(csv_path, measurement_slots)
            elif self.mode is LoggerMode.BUS: self.csv_writer = BusCsvStreamWriter(csv_path)
            elif self.mode is LoggerMode.MIXED: self.csv_writer = MixedCsvStreamWriter(csv_path)
            else: self.csv_writer = WaveformCsvStreamWriter(csv_path)
        if self.output_format in {LoggerOutputFormat.BINARY, LoggerOutputFormat.BOTH}:
            self.binary_writer = Dpo4LogWriter(self.root / f"{self.stem}.dpo4log", run_metadata=run_metadata)
        self.records_written = 0; self.bytes_written = 0; self._closed = False
    @property
    def paths(self) -> tuple[Path, ...]:
        result: list[Path] = []
        if self.csv_writer is not None: result.append(self.csv_writer.path)
        if self.binary_writer is not None: result.append(self.binary_writer.path)
        return tuple(result)
    def append(self, record: LoggerRecord) -> None:
        if self._closed: raise RuntimeError("Logger output session is closed.")
        if self.csv_writer is not None: self.csv_writer.append(record)
        if self.binary_writer is not None: self.binary_writer.append(record)
        self.records_written += 1; self.bytes_written = sum(path.stat().st_size for path in self.paths if path.exists())
    def close(self) -> None:
        if self._closed: return
        errors: list[BaseException] = []
        for writer in (self.csv_writer, self.binary_writer):
            if writer is None: continue
            try: writer.close()
            except BaseException as exc: errors.append(exc)
        self._closed = True; self.bytes_written = sum(path.stat().st_size for path in self.paths if path.exists())
        if errors: raise RuntimeError("; ".join(str(error) for error in errors))
__all__ = ["LoggerOutputSession"]
