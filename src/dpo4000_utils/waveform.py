"""Waveform acquisition and CSV export helpers."""

from __future__ import annotations

import csv


def parse_ascii_curve(raw_data: str) -> list[float]:
    """Parse an ASCII Tektronix CURVE? response into float samples."""
    return [float(value) for value in raw_data.strip().split(",") if value.strip()]


class WaveformMixin:
    """Mixin for CSV waveform export."""

    def _read_channel_waveform(self, channel: int):
        if channel < 1 or channel > 4:
            raise ValueError("Channel must be between 1 and 4.")

        scope = self.ensure_connected()
        scope.write(f"DATA:SOURCE CH{channel}")
        scope.write("DATA:ENC ASCII")

        raw_data = scope.query("CURVE?")
        waveform_data = parse_ascii_curve(raw_data)

        x_increment = float(scope.query("WFMPRE:XINCR?"))
        x_origin = float(scope.query("WFMPRE:XZERO?"))
        y_multiplier = float(scope.query("WFMPRE:YMULT?"))
        y_offset = float(scope.query("WFMPRE:YOFF?"))
        y_zero = float(scope.query("WFMPRE:YZERO?"))

        times = [x_origin + i * x_increment for i in range(len(waveform_data))]
        voltages = [(y_raw - y_offset) * y_multiplier + y_zero for y_raw in waveform_data]
        return times, voltages

    def save_waveform_to_csv(self, channel, filename):
        """Save waveform data from a specific channel to a CSV file."""
        times, voltages = self._read_channel_waveform(channel)

        with open(filename, mode="w", newline="") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(["Time (s)", "Voltage (V)"])
            writer.writerows(zip(times, voltages))

    def save_all_channels_to_csv(self, base_filename):
        """Save waveforms from all enabled channels to separate CSV files."""
        scope = self.ensure_connected()

        for channel in range(1, 5):
            channel_status = scope.query(f"SELECT:CH{channel}?").strip()
            if channel_status == "1":
                self.save_waveform_to_csv(channel, f"{base_filename}_CH{channel}.csv")

    def save_all_channels_to_single_csv(self, filename):
        """Save all enabled channel waveforms into a single CSV file."""
        scope = self.ensure_connected()
        channel_data = {}
        time_data = None

        for channel in range(1, 5):
            channel_status = scope.query(f"SELECT:CH{channel}?").strip()
            if channel_status != "1":
                continue

            times, voltages = self._read_channel_waveform(channel)

            if time_data is None:
                time_data = times

            label = scope.query(f"CH{channel}:LABEL?").strip()
            if not label:
                label = f"CH{channel}"
            channel_data[label] = voltages

        if time_data is None:
            raise RuntimeError("No enabled channels found.")

        with open(filename, mode="w", newline="") as csv_file:
            writer = csv.writer(csv_file)
            header = ["Time (s)"] + list(channel_data.keys())
            writer.writerow(header)

            for i in range(len(time_data)):
                row = [time_data[i]] + [channel_data[ch][i] for ch in channel_data.keys()]
                writer.writerow(row)
