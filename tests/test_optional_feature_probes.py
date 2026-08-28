from __future__ import annotations

import pytest

from dpo4000_utils.bus import BusMixin
from dpo4000_utils.reference import ReferenceMixin


class ProbeVisa:
    def __init__(self, responses: dict[str, str] | None = None):
        self.responses = responses or {}
        self.queries: list[str] = []

    def query(self, command: str) -> str:
        self.queries.append(command)
        if command not in self.responses:
            raise TimeoutError(f"no response for {command}")
        return self.responses[command]


class BusProbeDriver(BusMixin):
    def __init__(self, visa: ProbeVisa):
        self.visa = visa

    def ensure_connected(self):
        return self.visa


class ReferenceProbeDriver(ReferenceMixin):
    def __init__(self, visa: ProbeVisa):
        self.visa = visa

    def ensure_connected(self):
        return self.visa


def test_bus_probe_uses_one_required_type_query():
    visa = ProbeVisa({"BUS:B1:TYPE?": ":BUS:B1:TYPE I2C"})

    assert BusProbeDriver(visa).probe_bus_support(1) is True
    assert visa.queries == ["BUS:B1:TYPE?"]


def test_reference_probe_uses_one_required_display_query_even_when_ref_is_off():
    visa = ProbeVisa({"SELECT:REF1?": ":SELECT:REF1 0"})

    assert ReferenceProbeDriver(visa).probe_reference_support(1) is True
    assert visa.queries == ["SELECT:REF1?"]


def test_optional_feature_probes_propagate_timeout_for_fail_fast_discovery():
    with pytest.raises(TimeoutError):
        BusProbeDriver(ProbeVisa()).probe_bus_support(1)
    with pytest.raises(TimeoutError):
        ReferenceProbeDriver(ProbeVisa()).probe_reference_support(1)
