from __future__ import annotations

from pathlib import Path

import dpo4000_utils.instrument as instrument_module
from dpo4000_utils.instrument import DPO4000Scope


class FakeInstrument:
    def __init__(self) -> None:
        self.writes: list[str] = []

    def write(self, command: str) -> None:
        self.writes.append(command)


def test_restore_default_setup_matches_front_panel_factory_recall():
    scope = DPO4000Scope()
    instrument = FakeInstrument()
    scope.scope = instrument

    result = scope.restore_default_setup()

    assert result == "Scope default setup restored"
    assert instrument.writes == ["RECALL:SETUP FACTORY"]


def test_single_csv_wrapper_forwards_explicit_waveform_options(monkeypatch, tmp_path):
    scope = DPO4000Scope()
    captured: dict[str, object] = {}
    waveforms = {"CH1": object()}

    def read_enabled_waveforms(**kwargs):
        captured["waveform_options"] = kwargs
        return waveforms

    def write_waveforms_csv(path, values):
        captured["path"] = Path(path)
        captured["waveforms"] = values
        return Path(path)

    scope.read_enabled_waveforms = read_enabled_waveforms  # type: ignore[method-assign]
    monkeypatch.setattr(instrument_module, "write_waveforms_csv", write_waveforms_csv)
    output = tmp_path / "capture.csv"

    result = scope.save_all_channels_to_single_csv(output, point_count=100_000)

    assert result == output
    assert captured["waveform_options"] == {"point_count": 100_000}
    assert captured["path"] == output
    assert captured["waveforms"] is waveforms
