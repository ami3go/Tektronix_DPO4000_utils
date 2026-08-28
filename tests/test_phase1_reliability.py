from __future__ import annotations

import pytest

from dpo4000_utils import (
    DPOCleanupError,
    DPOConnectionError,
    DPONotConnectedError,
    DPO4000Scope,
)
from dpo4000_utils.connection import ConnectionMixin, temporary_session_attributes
from dpo4000_utils import connection
from dpo4000_utils.session import scope_session


class CloseProbe:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.closed = 0

    def close(self) -> None:
        self.closed += 1
        if self.fail:
            raise RuntimeError("close failed")


class LifecycleDriver(ConnectionMixin):
    def __init__(self, scope, rm) -> None:
        self.scope = scope
        self.rm = rm


def test_disconnect_clears_state_and_closes_rm_when_scope_close_fails():
    instrument = CloseProbe(fail=True)
    rm = CloseProbe()
    driver = LifecycleDriver(instrument, rm)

    with pytest.raises(DPOCleanupError, match="Failed to fully close VISA session"):
        driver.disconnect()

    assert instrument.closed == 1
    assert rm.closed == 1
    assert driver.scope is None
    assert driver.rm is None

    # Once state is cleared, repeated disconnect is idempotent.
    driver.disconnect()
    assert instrument.closed == 1
    assert rm.closed == 1


def test_temporary_attributes_restore_exact_none_values():
    class Session:
        timeout = None
        read_termination = None

    session = Session()
    with temporary_session_attributes(session, timeout=1234, read_termination="\n"):
        assert session.timeout == 1234
        assert session.read_termination == "\n"

    assert session.timeout is None
    assert session.read_termination is None


def test_not_connected_uses_stable_public_exception():
    driver = LifecycleDriver(None, None)
    with pytest.raises(DPONotConnectedError):
        driver.ensure_connected()


def test_default_driver_construction_has_no_io_or_filesystem_side_effect(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    scope = DPO4000Scope()

    assert scope.scope is None
    assert scope.rm is None
    assert scope.resource_name is None
    assert not (tmp_path / "scope_settings").exists()

    with pytest.raises(DPOConnectionError, match="No VISA resource"):
        scope.connect()


class FailingCloseInstrument:
    def __init__(self) -> None:
        self.timeout = 1000
        self.read_termination = None
        self.write_termination = None

    def query(self, command: str) -> str:
        assert command == "*IDN?"
        return "TEKTRONIX,DPO4054,TEST,1.0"

    def close(self) -> None:
        raise RuntimeError("instrument close failed")


class SessionResourceManager:
    def __init__(self, instrument) -> None:
        self.instrument = instrument
        self.closed = False

    def open_resource(self, resource_name: str):
        assert resource_name == "TEST::INSTR"
        return self.instrument

    def close(self) -> None:
        self.closed = True


class FakeVisa:
    def __init__(self, rm) -> None:
        self.rm = rm

    def ResourceManager(self):  # noqa: N802 - PyVISA API shape.
        return self.rm


def test_scope_session_preserves_body_exception_when_cleanup_also_fails(monkeypatch):
    instrument = FailingCloseInstrument()
    rm = SessionResourceManager(instrument)
    monkeypatch.setattr(connection, "pyvisa", FakeVisa(rm))

    with pytest.raises(ValueError, match="primary body failure"):
        with scope_session("TEST::INSTR"):
            raise ValueError("primary body failure")

    assert rm.closed is True
