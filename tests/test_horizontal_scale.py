import pytest

from dpo4000_utils import DPO4054
from dpo4000_utils.control import (
    build_horizontal_scale_command,
    build_horizontal_scale_query,
)


class FakeInstrument:
    def __init__(self) -> None:
        self.writes = []

    def write(self, command: str) -> None:
        self.writes.append(command)

    def query(self, command: str) -> str:
        assert command == "HORIZONTAL:SCALE?"
        return "0.002"


def test_horizontal_scale_command_validation() -> None:
    assert build_horizontal_scale_command(0.002) == "HORIZONTAL:SCALE 0.002"
    assert build_horizontal_scale_query() == "HORIZONTAL:SCALE?"
    with pytest.raises(ValueError):
        build_horizontal_scale_command(0)


def test_scope_horizontal_scale_round_trip() -> None:
    scope = DPO4054(auto_connect=False)
    fake = FakeInstrument()
    scope.scope = fake

    scope.set_horizontal_scale(0.005)

    assert fake.writes == ["HORIZONTAL:SCALE 0.005"]
    assert scope.get_horizontal_scale() == pytest.approx(0.002)
