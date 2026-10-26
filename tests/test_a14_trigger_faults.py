"""A14 malformed-reply and lost-connection behavior for trigger APIs."""

from __future__ import annotations

import pytest

from dpo4000_utils.errors import DPONotConnectedError, DPOTransportError

from test_advanced_trigger import FakeInstrument, FakeScope, _edge_config


class _WriteFailsInstrument(FakeInstrument):
    def __init__(self, *args, fail_on: str, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fail_on = fail_on

    def write(self, command: str) -> None:
        if command.startswith(self.fail_on):
            raise ConnectionError("USB device disconnected")
        super().write(command)


@pytest.mark.parametrize("reply", ["", "   ", "\n"])
def test_empty_trigger_level_reply_is_a_clear_error(reply: str) -> None:
    scope = FakeScope({"TRIGGER:A:LEVEL:CH1?": reply})
    with pytest.raises(ValueError, match="Empty trigger level response"):
        scope.get_trigger_level(channel=1)


def test_non_numeric_trigger_level_keeps_legacy_raw_text() -> None:
    scope = FakeScope({"TRIGGER:A:LEVEL?": ":TRIGGER:A:LEVEL TTL"})
    assert scope.get_trigger_level() == ":TRIGGER:A:LEVEL TTL"


@pytest.mark.parametrize("reply", ["", "garbage", ":TRIGGER:A:HOLDOFF:VALUE"])
def test_malformed_holdoff_reply_raises(reply: str) -> None:
    scope = FakeScope({"TRIGGER:A:HOLDOFF:VALUE?": reply})
    with pytest.raises(ValueError, match="Invalid trigger holdoff response"):
        scope.get_trigger_holdoff()


def test_empty_edge_readbacks_do_not_crash() -> None:
    scope = FakeScope(
        {
            "TRIGGER:A:EDGE:SOURCE?": "",
            "TRIGGER:A:MODE?": "",
            "TRIGGER:A:EDGE:SLOPE?": "",
            "TRIGGER:A:EDGE:COUPLING?": "",
            "TRIGGER:A:LEVEL?": "",
        }
    )
    assert scope.get_edge_trigger_configuration() == {
        "mode": "",
        "source": "",
        "slope": "",
        "coupling": "",
        "level": "",
    }


def test_disconnect_during_configure_propagates_and_skips_holdoff() -> None:
    scope = FakeScope()
    scope.scope = _WriteFailsInstrument(fail_on="TRIGGER:A:EDGE:SOURCE")
    with pytest.raises(ConnectionError):
        scope.configure_trigger(_edge_config(), holdoff=0.001)
    assert not any("HOLDOFF" in command for command in scope.scope.writes)


def test_disconnect_during_readback_propagates() -> None:
    scope = FakeScope({"TRIGGER:A:HOLDOFF:VALUE?": ConnectionError("link lost")})
    with pytest.raises(ConnectionError):
        scope.get_trigger_holdoff()


def test_probe_disconnect_is_transport_error_and_timeout_is_restored() -> None:
    scope = FakeScope({"TRIGGER:B:EVENTS:MODE?": ConnectionError("link lost")}, timeout=20_000)
    with pytest.raises(DPOTransportError):
        scope.probe_scpi_query("TRIGGER:B:EVENTS:MODE?", timeout_ms=300)
    assert scope.scope.timeout == 20_000


def test_probe_recovery_failure_after_timeout_is_transport_error_and_restores_timeout() -> None:
    scope = FakeScope(
        {
            "TRIGGER:B:EVENTS:MODE?": TimeoutError("timed out"),
            "*IDN?": ConnectionError("link lost during recovery"),
        },
        timeout=15_000,
    )
    with pytest.raises(DPOTransportError):
        scope.probe_scpi_query("TRIGGER:B:EVENTS:MODE?", timeout_ms=300)
    assert scope.scope.timeout == 15_000


def test_trigger_calls_without_session_raise_not_connected() -> None:
    scope = FakeScope()
    scope.scope = None
    for call in (
        lambda: scope.get_trigger_level(),
        lambda: scope.get_trigger_holdoff(),
        lambda: scope.configure_trigger(_edge_config()),
        lambda: scope.probe_scpi_query("TRIGGER:A:MODE?"),
    ):
        with pytest.raises(DPONotConnectedError):
            call()


def test_rearm_after_image_does_not_hide_a_lost_connection(monkeypatch) -> None:
    import dpo4000_utils.trigger as trigger_module

    monkeypatch.setattr(trigger_module.time, "sleep", lambda _s: None)
    scope = FakeScope({"TRIGGER:A:MODE?": ConnectionError("link lost")})
    with pytest.raises(ConnectionError):
        scope.rearm_trigger_after_image()
    assert scope.scope.writes == []


def test_rearm_after_image_still_tolerates_malformed_readbacks(monkeypatch) -> None:
    import dpo4000_utils.trigger as trigger_module

    monkeypatch.setattr(trigger_module.time, "sleep", lambda _s: None)
    scope = FakeScope({"TRIGGER:A:MODE?": "", "TRIGGER:A:LEVEL?": "garbage"})
    scope.rearm_trigger_after_image()
    assert scope.scope.writes == ["ACQUIRE:STATE RUN"]
