from __future__ import annotations

from array import array

from dpo4000_utils.waveform import WaveformRequest, read_waveform


class ReducedOutgoingWaveformScope:
    """Model a long DPO4054 record whose CURVE transfer is scope-reduced."""

    def __init__(self) -> None:
        self.data_start = 1
        self.data_stop = 8
        self.record_length = 8
        self.width = 2
        self.encoding = "RIBINARY"
        self.current_source = "CH1"
        self.binary_calls: list[tuple[str, dict[str, object]]] = []
        self.writes: list[str] = []

    def write(self, command: str) -> None:
        self.writes.append(command)
        if command.startswith("DATA:SOURCE "):
            self.current_source = command.split()[-1]
        elif command.startswith("DATA:START "):
            self.data_start = max(1, min(int(command.split()[-1]), self.record_length))
        elif command.startswith("DATA:STOP "):
            self.data_stop = max(1, min(int(command.split()[-1]), self.record_length))
        elif command.startswith("DATA:WIDTH "):
            self.width = int(command.split()[-1])
        elif command.startswith("DATA:ENCDG "):
            self.encoding = command.split()[-1]

    def query(self, command: str) -> str:
        responses = {
            "DATA:START?": str(self.data_start),
            "DATA:STOP?": str(self.data_stop),
            "WFMOUTPRE:BYT_NR?": str(self.width),
            "WFMOUTPRE:ENCDG?": "BIN",
            "WFMOUTPRE:BN_FMT?": "RI",
            "WFMOUTPRE:BYT_OR?": "MSB",
            # Real DPO4054 self-test evidence: the selected source range may be
            # larger than the outgoing CURVE representation.
            "WFMOUTPRE:NR_PT?": "4",
            "WFMOUTPRE:PT_FMT?": "Y",
            "WFMOUTPRE:XUNIT?": '"s"',
            "WFMOUTPRE:XINCR?": "0.5",
            "WFMOUTPRE:XZERO?": "1.0",
            "WFMOUTPRE:PT_OFF?": "0",
            "WFMOUTPRE:YUNIT?": '"V"',
            "WFMOUTPRE:YMULT?": "0.1",
            "WFMOUTPRE:YOFF?": "0",
            "WFMOUTPRE:YZERO?": "0",
            "CH1:LABEL?": '"Input"',
        }
        if command not in responses:
            raise AssertionError(f"Unexpected query: {command}")
        return responses[command]

    def query_binary_values(self, message: str, **kwargs):
        self.binary_calls.append((message, dict(kwargs)))
        assert message == "CURVE?"
        assert kwargs["data_points"] == 4
        return kwargs["container"]((10, 20, 30, 40))


def test_long_selected_record_accepts_scope_reduced_outgoing_curve_count():
    scope = ReducedOutgoingWaveformScope()

    waveform = read_waveform(scope, WaveformRequest(source="CH1"))

    # The selected source-record range remains explicit and fully verified.
    assert waveform.start_index == 1
    assert waveform.stop_index == 8
    # The actual transfer count comes from WFMOUTPRE:NR_PT.
    assert waveform.preamble.record_point_count == 4
    assert waveform.sample_count == 4
    assert list(waveform.samples) == [10, 20, 30, 40]
    assert scope.binary_calls[0][1]["data_points"] == 4
