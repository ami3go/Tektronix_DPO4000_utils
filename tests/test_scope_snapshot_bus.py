from __future__ import annotations

from dpo4000_utils.scope_snapshot import read_scope_snapshot


class FakeScope:
    def get_bus_configuration(self, bus: int):
        return {
            "state": "1",
            "type": "I2C",
            "label": f"BUS{bus}",
            "protocol": {"clock_source": "CH1", "data_source": "CH2"},
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


def test_scope_snapshot_reads_bus1_through_bus4_without_analog_or_ref_reads():
    snapshot = read_scope_snapshot(
        FakeScope(),
        channels=(),
        references=(),
        buses=(1, 2, 3, 4),
    )

    assert set(snapshot["buses"]) == {1, 2, 3, 4}
    assert snapshot["buses"][4]["label"] == "BUS4"
    assert snapshot["buses"][1]["protocol"]["clock_source"] == "CH1"
    assert snapshot["errors"] == {}


def test_scope_snapshot_isolates_one_bus_read_failure():
    class PartialScope(FakeScope):
        def get_bus_configuration(self, bus: int):
            if bus == 2:
                raise RuntimeError("BUS2 option unavailable")
            return super().get_bus_configuration(bus)

    snapshot = read_scope_snapshot(
        PartialScope(),
        channels=(),
        references=(),
        buses=(1, 2, 3),
    )

    assert set(snapshot["buses"]) == {1, 3}
    assert snapshot["errors"]["bus.bus2"] == "BUS2 option unavailable"
