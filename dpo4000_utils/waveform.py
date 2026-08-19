"""Waveform acquisition and CSV export helpers."""

from __future__ import annotations

import csv
from collections.abc import Iterable, Sequence
from pathlib import Path


def validate_channel(channel: int) -> int:
    """Return a valid DPO4000 channel number or raise ``ValueError``."""
    try:
        channel_number = int(channel)
    except Exception as exc:
        raise ValueError("Channel must be between 1 and 4.") from exc
    if channel_number < 1 or channel_number > 4:
        raise ValueError("Channel must be between 1 and 4.")
    return channel_number


def parse_ascii_curve(raw_data: str) -> list[float]:
    """Parse an ASCII Tektronix ``CURVE?`` response into float samples."""
    return [float(value) for value in raw_data.strip().split(",") if value.strip()]


def parse_channel_enabled(response: str) -> bool:
    """Return whether a ``SELECT:CHn?`` response means the channel is enabled."""
    return response.strip().upper() in {"1", "ON", "TRUE"}


def normalize_channel_label(response: str, channel: int) -> str:
    """Return a CSV-safe channel label with a CHn fallback."""
    label = response.strip()
    if len(label) >= 2 and label[0] == label[-1] == '"':
        label = label[1:-1]
    return label or f"CH{validate_channel(channel)}"


def scale_waveform_samples(
    raw_samples: Sequence[float],
    *,
    x_increment: float,
    x_origin: float,
    y_multiplier: float,
    y_offset: float,
    y_zero: float,
) -> tuple[list[float], list[float]]:
    """Scale raw Tektronix waveform samples into time and voltage arrays."""
    times = [x_origin + i * x_increment for i in range(len(raw_samples))]
    voltages = [(sample - y_offset) * y_multiplier + y_zero for sample in raw_samples]
    return times, voltages


def read_channel_waveform(scope, channel: int) -> tuple[list[float], list[float]]:
    """Read and scale one channel waveform from a connected VISA-like scope."""
    channel = validate_channel(channel)
    scope.write(f"DATA:SOURCE CH{channel}")
    scope.write("DATA:ENC ASCII")

    raw_samples = parse_ascii_curve(scope.query("CURVE?"))
    return scale_waveform_samples(
        raw_samples,
        x_increment=float(scope.query("WFMPRE:XINCR?")),
        x_origin=float(scope.query("WFMPRE:XZERO?")),
        y_multiplier=float(scope.query("WFMPRE:YMULT?")),
        y_offset=float(scope.query("WFMPRE:YOFF?")),
        y_zero=float(scope.query("WFMPRE:YZERO?")),
    )


def enabled_channels(scope, channels: Iterable[int] = range(1, 5)) -> list[int]:
    """Return enabled channel numbers from ``SELECT:CHn?`` queries."""
    result: list[int] = []
    for channel in channels:
        channel = validate_channel(channel)
        if parse_channel_enabled(scope.query(f"SELECT:CH{channel}?").strip()):
            result.append(channel)
    return result


def read_enabled_channel_waveforms(
    scope,
    channels: Iterable[int] = range(1, 5),
) -> tuple[list[float], dict[str, list[float]]]:
    """Read enabled channels and return shared time data plus labelled voltages."""
    time_data: list[float] | None = None
    channel_data: dict[str, list[float]] = {}

    for channel in enabled_channels(scope, channels):
        times, voltages = read_channel_waveform(scope, channel)
        if time_data is None:
            time_data = times

        try:
            label_response = scope.query(f"CH{channel}:LABEL?")
        except Exception:
            label_response = ""
        label = normalize_channel_label(label_response, channel)
        channel_data[label] = voltages

    if time_data is None:
        raise RuntimeError("No enabled channels found.")

    return time_data, channel_data


def write_single_channel_csv(path: str | Path, times: Sequence[float], voltages: Sequence[float]) -> Path:
    """Write one channel waveform CSV file and return the written path."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["Time (s)", "Voltage (V)"])
        writer.writerows(zip(times, voltages))
    return output_path


def write_multi_channel_csv(
    path: str | Path,
    times: Sequence[float],
    channel_data: dict[str, Sequence[float]],
) -> Path:
    """Write a combined waveform CSV file and return the written path."""
    if not channel_data:
        raise RuntimeError("No enabled channels found.")

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    channel_names = list(channel_data.keys())
    with output_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(["Time (s)", *channel_names])
        for index, time_value in enumerate(times):
            writer.writerow([time_value, *[channel_data[name][index] for name in channel_names]])
    return output_path


def save_channel_waveform_csv(scope, channel: int, filename: str | Path) -> Path:
    """Read one channel waveform from a connected scope and save it as CSV."""
    times, voltages = read_channel_waveform(scope, channel)
    return write_single_channel_csv(filename, times, voltages)


def save_enabled_channels_to_single_csv(scope, filename: str | Path) -> Path:
    """Read all enabled channel waveforms from a connected scope and save one CSV."""
    times, channel_data = read_enabled_channel_waveforms(scope)
    return write_multi_channel_csv(filename, times, channel_data)


def save_enabled_channels_to_separate_csv(scope, base_filename: str | Path) -> list[Path]:
    """Read all enabled channel waveforms and save one CSV file per channel."""
    base_path = Path(base_filename)
    written: list[Path] = []
    for channel in enabled_channels(scope):
        output_path = base_path.with_name(f"{base_path.name}_CH{channel}.csv")
        written.append(save_channel_waveform_csv(scope, channel, output_path))
    return written


class WaveformMixin:
    """Mixin for CSV waveform export."""

    def _read_channel_waveform(self, channel: int):
        """Read waveform data from one channel using the connected instrument."""
        return read_channel_waveform(self.ensure_connected(), channel)

    def save_waveform_to_csv(self, channel, filename):
        """Save waveform data from a specific channel to a CSV file."""
        return save_channel_waveform_csv(self.ensure_connected(), channel, filename)

    def save_all_channels_to_csv(self, base_filename):
        """Save waveforms from all enabled channels to separate CSV files."""
        return save_enabled_channels_to_separate_csv(self.ensure_connected(), base_filename)

    def save_all_channels_to_single_csv(self, filename):
        """Save all enabled channel waveforms into a single CSV file."""
        return save_enabled_channels_to_single_csv(self.ensure_connected(), filename)
