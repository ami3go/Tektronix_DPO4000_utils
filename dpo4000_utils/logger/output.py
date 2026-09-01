"""Logger output-session multiplexer for CSV and DPO4LOG."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .csv_stream import WaveformCsvStreamWriter
from .dpo4log import Dpo4LogWriter
from .models import LoggerOutputFormat, LoggerRecord


class LoggerOutputSession:
    """Own the output writers for one Logger run."""

    def __init__(
        self,
        root: str | Path,
        output_format: LoggerOutputFormat,
        *,
        run_metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)
        self.output_format = LoggerOutputFormat(output_format)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        self.stem = f"logger_{stamp}_0000"
        self.csv_writer: WaveformCsvStreamWriter | None = None
        self.binary_writer: Dpo4LogWriter | None = None
        if self.output_format in {LoggerOutputFormat.CSV, LoggerOutputFormat.BOTH}:
            self.csv_writer = WaveformCsvStreamWriter(self.root / f"{self.stem}.csv")
        if self.output_format in {LoggerOutputFormat.BINARY, LoggerOutputFormat.BOTH}:
            self.binary_writer = Dpo4LogWriter(
                self.root / f"{self.stem}.dpo4log",
                run_metadata=run_metadata,
            )
        self.records_written = 0
        self.bytes_written = 0
        self._closed = False

    @property
    def paths(self) -> tuple[Path, ...]:
        result: list[Path] = []
        if self.csv_writer is not None:
            result.append(self.csv_writer.path)
        if self.binary_writer is not None:
            result.append(self.binary_writer.path)
        return tuple(result)

    def append(self, record: LoggerRecord) -> None:
        if self._closed:
            raise RuntimeError("Logger output session is closed.")
        if self.csv_writer is not None:
            self.csv_writer.append(record)
        if self.binary_writer is not None:
            self.binary_writer.append(record)
        self.records_written += 1
        self.bytes_written = sum(path.stat().st_size for path in self.paths if path.exists())

    def close(self) -> None:
        if self._closed:
            return
        errors: list[BaseException] = []
        for writer in (self.csv_writer, self.binary_writer):
            if writer is None:
                continue
            try:
                writer.close()
            except BaseException as exc:  # preserve both close failures if needed.
                errors.append(exc)
        self._closed = True
        self.bytes_written = sum(path.stat().st_size for path in self.paths if path.exists())
        if errors:
            raise RuntimeError("; ".join(str(error) for error in errors))


__all__ = ["LoggerOutputSession"]
