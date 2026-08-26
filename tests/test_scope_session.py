from __future__ import annotations

from dpo4000_utils import connection
from dpo4000_utils.session import scope_session


class FakeInstrument:
    def __init__(self) -> None:
        self.timeout = 111
        self.read_termination = None
        self.write_termination = None
        self.closed = False
        self.idn_query_snapshot = None

    def query(self, command: str) -> str:
        assert command == "*IDN?"
        self.idn_query_snapshot = (
            self.timeout,
            self.read_termination,
            self.write_termination,
        )
        return "TEKTRONIX,DPO4054,TEST,1.0"

    def close(self) -> None:
        self.closed = True


class FakeResourceManager:
    def __init__(self, instrument: FakeInstrument) -> None:
        self.instrument = instrument
        self.opened_resource = None
        self.closed = False

    def open_resource(self, resource_name: str) -> FakeInstrument:
        self.opened_resource = resource_name
        return self.instrument

    def close(self) -> None:
        self.closed = True


class FakeVisa:
    def __init__(self, resource_manager: FakeResourceManager) -> None:
        self.resource_manager = resource_manager

    def ResourceManager(self) -> FakeResourceManager:  # noqa: N802 - PyVISA API shape.
        return self.resource_manager


def test_scope_session_configures_before_idn_and_always_closes(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    instrument = FakeInstrument()
    rm = FakeResourceManager(instrument)
    monkeypatch.setattr(connection, "pyvisa", FakeVisa(rm))

    with scope_session(
        "TCPIP0::192.0.2.10::4000::SOCKET",
        timeout_ms=45_000,
        read_termination="\n",
        write_termination="\n",
    ) as scope:
        assert scope.query_identity() == "TEKTRONIX,DPO4054,TEST,1.0"
        assert rm.opened_resource == "TCPIP0::192.0.2.10::4000::SOCKET"
        assert instrument.idn_query_snapshot == (45_000, "\n", "\n")

    assert instrument.closed is True
    assert rm.closed is True


def test_invalid_timeout_closes_failed_connection(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    instrument = FakeInstrument()
    rm = FakeResourceManager(instrument)
    monkeypatch.setattr(connection, "pyvisa", FakeVisa(rm))

    try:
        with scope_session("TEST::INSTR", timeout_ms=0):
            raise AssertionError("session should not open with timeout_ms=0")
    except ConnectionError as exc:
        assert "timeout_ms must be a positive integer" in str(exc)

    assert instrument.closed is True
    assert rm.closed is True
