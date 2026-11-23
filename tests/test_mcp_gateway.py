"""No-VISA offline tests of the MCP gateway's public read-only boundary."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Event, get_ident

import pytest

from dpo4000_utils.mcp_server.gateway import (
    ReadOnlyGateway,
    ScopeBusyError,
    ScopeGatewayClosedError,
    ScopeIOForbiddenError,
)


@dataclass
class FakeMeasurement:
    slot: int
    state: str
    value: str


class FakeScope:
    def __init__(self):
        self.calls = []
        self.thread_ids = []
        self.started = None
        self.unblock = None

    def query_identity(self):
        self.calls.append("identity")
        self.thread_ids.append(get_ident())
        if self.started is not None:
            self.started.set()
            assert self.unblock.wait(timeout=5)
        return "TEKTRONIX,DPO4054,FAKE,0.0"

    def get_channel_configuration(self, channel):
        self.calls.append(("channel", channel))
        self.thread_ids.append(get_ident())
        return {"label": f"CH{channel}"}

    def get_all_measurement_setups(self):
        self.calls.append("measurements")
        self.thread_ids.append(get_ident())
        return {1: FakeMeasurement(slot=1, state="ON", value="1.2")}

    def get_trigger_configuration(self):
        self.calls.append("trigger")
        self.thread_ids.append(get_ident())
        return {"trigger_type": "EDGE"}

    def get_acquisition_setup(self):
        self.calls.append("acquisition")
        self.thread_ids.append(get_ident())
        return {"mode": "SAMPLE"}


def make_factory(scope, events):
    @contextmanager
    def session(resource):
        events.append(("open", resource, get_ident()))
        try:
            yield scope
        finally:
            events.append(("close", resource, get_ident()))

    return session


def test_disabled_gateway_never_opens_a_session():
    events = []
    gateway = ReadOnlyGateway(session_factory=make_factory(FakeScope(), events))
    try:
        assert gateway.status()["instrument_io_enabled"] is False
        with pytest.raises(ScopeIOForbiddenError):
            asyncio.run(gateway.execute("identity"))
        assert events == []
    finally:
        gateway.close()


def test_fake_instrument_uses_one_retained_worker_session():
    events = []
    scope = FakeScope()
    gateway = ReadOnlyGateway(
        "USB::FAKE::INSTR",
        allow_instrument_io=True,
        session_factory=make_factory(scope, events),
    )
    async def run():
        assert (await gateway.execute("identity"))["idn"].startswith("TEKTRONIX")
        assert len((await gateway.execute("channels"))["channels"]) == 4
        assert (await gateway.execute("measurement_slots"))["measurement_slots"]["1"]["value"] == "1.2"
        assert (await gateway.execute("trigger"))["trigger"]["trigger_type"] == "EDGE"
        assert (await gateway.execute("acquisition"))["acquisition"]["mode"] == "SAMPLE"

    try:
        asyncio.run(run())
        assert [event[0] for event in events] == ["open"]
        assert len(set(scope.thread_ids)) == 1
        assert events[0][2] == scope.thread_ids[0]
    finally:
        gateway.close()
    assert [event[0] for event in events] == ["open", "close"]
    assert events[1][2] == events[0][2]


def test_busy_rejects_overlapping_requests_without_queueing():
    events = []
    scope = FakeScope()
    scope.started = Event()
    scope.unblock = Event()
    gateway = ReadOnlyGateway(
        "USB::FAKE::INSTR",
        allow_instrument_io=True,
        session_factory=make_factory(scope, events),
    )

    async def run():
        first = asyncio.create_task(gateway.execute("identity"))
        assert await asyncio.to_thread(scope.started.wait, 2)
        with pytest.raises(ScopeBusyError):
            await gateway.execute("acquisition")
        scope.unblock.set()
        assert (await first)["idn"].startswith("TEKTRONIX")

    try:
        asyncio.run(run())
        assert scope.calls == ["identity"]
    finally:
        scope.unblock.set()
        gateway.close()


def test_capture_validation_rejects_before_instrument_io():
    events = []
    gateway = ReadOnlyGateway(
        "USB::FAKE::INSTR",
        allow_instrument_io=True,
        session_factory=make_factory(FakeScope(), events),
    )
    try:
        async def reject():
            for params in (
                {"max_points": 1_001, "preview_points": 10},
                {"max_points": 10, "preview_points": 257},
                {"max_points": True, "preview_points": 10},
            ):
                with pytest.raises(ValueError):
                    await gateway.execute("capture_preconfigured", **params)
            with pytest.raises(ValueError):
                await gateway.execute("connect")
        asyncio.run(reject())
        assert events == []
    finally:
        gateway.close()


def test_closed_gateway_rejects_io():
    gateway = ReadOnlyGateway("USB::FAKE::INSTR", allow_instrument_io=True)
    gateway.close()
    with pytest.raises(ScopeGatewayClosedError):
        asyncio.run(gateway.execute("identity"))


def test_cancellation_does_not_release_physical_busy_lease():
    scope = FakeScope()
    scope.started = Event()
    scope.unblock = Event()
    gateway = ReadOnlyGateway(
        "USB::FAKE::INSTR",
        allow_instrument_io=True,
        session_factory=make_factory(scope, []),
    )

    async def run():
        task = asyncio.create_task(gateway.execute("identity"))
        assert await asyncio.to_thread(scope.started.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(ScopeBusyError):
            await gateway.execute("trigger")
        scope.unblock.set()
        for _ in range(50):
            if not gateway.status()["busy"]:
                break
            await asyncio.sleep(0.01)
        assert not gateway.status()["busy"]
        assert (await gateway.execute("trigger"))["trigger"]["trigger_type"] == "EDGE"

    try:
        asyncio.run(run())
    finally:
        scope.unblock.set()
        gateway.close()
