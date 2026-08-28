from __future__ import annotations

from dpo4000_utils.scope_snapshot import read_scope_snapshot


class FakeScope:
    def get_channel_label(self, channel: int):
        return f"CH{channel}"

    def get_channel_configuration(self, channel: int):
        return {"display": "ON", "scale": "1"}

    def get_reference_configuration(self, reference: int):
        return {
            "display": "ON" if reference == 1 else "OFF",
            "label": f"REF-{reference}",
            "vertical_scale": str(reference),
            "date": "28-AUG-2026",
            "time": "10:00:00",
        }

    def get_math_configuration(self):
        return {}

    def get_all_measurement_setups(self):
        return {}

    def get_edge_trigger_configuration(self):
        return {}

    def get_horizontal_position(self):
        return 0.0

    def get_acquisition_setup(self):
        return {}

    def get_display_settings(self):
        return {}


def test_scope_snapshot_reads_reference_waveforms_in_same_session():
    snapshot = read_scope_snapshot(
        FakeScope(),
        channels=(1,),
        references=(1, 2),
    )

    assert snapshot["references"][1]["display"] == "ON"
    assert snapshot["references"][1]["label"] == "REF-1"
    assert snapshot["references"][2]["vertical_scale"] == "2"
    assert snapshot["errors"] == {}


def test_scope_snapshot_isolates_one_reference_read_failure():
    class PartialScope(FakeScope):
        def get_reference_configuration(self, reference: int):
            if reference == 2:
                raise RuntimeError("REF2 empty")
            return super().get_reference_configuration(reference)

    snapshot = read_scope_snapshot(
        PartialScope(),
        channels=(1,),
        references=(1, 2, 3),
    )

    assert snapshot["references"][1]["label"] == "REF-1"
    assert 2 not in snapshot["references"]
    assert snapshot["references"][3]["label"] == "REF-3"
    assert snapshot["errors"]["reference.ref2"] == "REF2 empty"
