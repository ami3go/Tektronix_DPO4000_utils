from __future__ import annotations

from dpo4000_utils.connection import ConnectionMixin
from dpo4000_utils.scope_snapshot import DEFAULT_OPTIONAL_FEATURE_TIMEOUT_MS, read_scope_snapshot


class FakeInstrument:
    def __init__(self, timeout: int = 20_000):
        self.timeout = timeout


class OptionalFeatureScope(ConnectionMixin):
    def __init__(self):
        self.scope = FakeInstrument()
        self.reference_reads = 0
        self.bus_reads = 0
        self.probe_timeouts: list[tuple[str, int]] = []

    def get_channel_label(self, channel: int):
        return f"CH{channel}"

    def get_channel_configuration(self, channel: int):
        return {"display": "1"}

    def probe_reference_support(self, reference: int):
        self.probe_timeouts.append(("reference", self.scope.timeout))
        raise TimeoutError("reference option did not answer")

    def get_reference_configuration(self, reference: int):
        self.reference_reads += 1
        return {}

    def probe_bus_support(self, bus: int):
        self.probe_timeouts.append(("bus", self.scope.timeout))
        raise TimeoutError("bus option did not answer")

    def get_bus_configuration(self, bus: int):
        self.bus_reads += 1
        return {}

    def get_math_configuration(self):
        return {}

    def get_all_measurement_setups(self):
        return {}

    def get_edge_trigger_configuration(self):
        return {}

    def get_horizontal_position(self):
        return 0

    def get_acquisition_setup(self):
        return {}

    def get_display_settings(self):
        return {}


def test_temporary_timeout_caps_and_restores_visa_timeout_on_error():
    scope = OptionalFeatureScope()

    try:
        with scope.temporary_timeout(1500):
            assert scope.scope.timeout == 1500
            raise RuntimeError("stop")
    except RuntimeError:
        pass

    assert scope.scope.timeout == 20_000


def test_snapshot_probes_optional_families_once_and_does_not_expand_timeouts():
    scope = OptionalFeatureScope()

    snapshot = read_scope_snapshot(
        scope,
        channels=(),
        references=(1, 2, 3, 4),
        buses=(1, 2, 3, 4),
    )

    assert scope.probe_timeouts == [
        ("reference", DEFAULT_OPTIONAL_FEATURE_TIMEOUT_MS),
        ("bus", DEFAULT_OPTIONAL_FEATURE_TIMEOUT_MS),
    ]
    assert scope.reference_reads == 0
    assert scope.bus_reads == 0
    assert scope.scope.timeout == 20_000
    assert snapshot["errors"]["reference.support"] == "reference option did not answer"
    assert snapshot["errors"]["bus.support"] == "bus option did not answer"
    assert snapshot["horizontal_position"] == 0
