"""optional_query must not leave a session reading one response behind.

A timed-out query is not an abandoned one: the instrument still produces the
answer, it just goes unread. If the health probe runs without clearing first it
reads that leftover answer, concludes the session is healthy, and every following
query returns the previous command's response -- for good, not just once.
"""

from __future__ import annotations

from collections import deque

import pytest

from dpo4000_utils.errors import DPOTimeoutError, DPOTransportError
from dpo4000_utils.io_policy import optional_query, required_query

SLOW_COMMAND = "CH1:LABEL?"


class FakeTimeout(Exception):
    """Shaped like a PyVISA timeout as errors.is_transport_error recognises it."""

    error_code = -1073807339  # VI_ERROR_TMO


class DesyncingInstrument:
    """Models unread responses as a queue, which is what makes the shift persistent.

    Every query makes the instrument produce an answer. A timeout means the driver
    gave up reading it, not that it was never produced -- so it stays queued and the
    next read collects it instead of its own answer.
    """

    def __init__(self, *, supports_clear: bool = True, probe_ok: bool = True) -> None:
        self.events: list[str] = []
        self.probe_ok = probe_ok
        self.last_produced = ""
        self._unread: deque[str] = deque()
        self._seq = 0
        if supports_clear:
            self.clear = self._clear

    def _clear(self) -> None:
        self.events.append("clear")
        self._unread.clear()

    def query(self, command: str) -> str:
        self.events.append(f"query:{command}")
        self._seq += 1
        self.last_produced = f"{command}->answer{self._seq}"
        self._unread.append(self.last_produced)
        if command == SLOW_COMMAND or not self.probe_ok:
            raise FakeTimeout("VI_ERROR_TMO: Timeout expired before operation completed.")
        return self._unread.popleft()


def test_pending_response_is_discarded_before_the_health_probe():
    instrument = DesyncingInstrument()

    assert optional_query(instrument, SLOW_COMMAND) == ""

    assert instrument.events == [f"query:{SLOW_COMMAND}", "clear", "query:*IDN?"]
    assert instrument.events.index("clear") < instrument.events.index("query:*IDN?")


def test_the_probe_reads_its_own_answer_not_the_timed_out_one():
    instrument = DesyncingInstrument()

    optional_query(instrument, SLOW_COMMAND)

    # The probe is the second query; without clearing it would have read the first.
    assert instrument.events == [f"query:{SLOW_COMMAND}", "clear", "query:*IDN?"]
    assert not instrument._unread, "a leftover response would shift every later query"


def test_later_queries_are_not_shifted_by_one():
    """The real harm: a whole readback scan silently reporting the previous value."""
    instrument = DesyncingInstrument()
    optional_query(instrument, SLOW_COMMAND)

    for _ in range(3):
        identity = required_query(instrument, "*IDN?")
        assert identity == instrument.last_produced, (
            f"query returned a stale answer: got {identity!r}, "
            f"expected {instrument.last_produced!r}"
        )


def test_instrument_without_clear_is_tolerated():
    instrument = DesyncingInstrument(supports_clear=False)

    assert optional_query(instrument, SLOW_COMMAND) == ""
    assert "clear" not in instrument.events


def test_failed_health_probe_still_raises_transport_error():
    instrument = DesyncingInstrument(probe_ok=False)

    with pytest.raises((DPOTransportError, DPOTimeoutError)):
        optional_query(instrument, SLOW_COMMAND)


def test_clear_failure_does_not_mask_the_original_handling():
    class ExplodingClear(DesyncingInstrument):
        def _clear(self) -> None:
            self.events.append("clear")
            raise RuntimeError("device clear not supported on this transport")

    instrument = ExplodingClear()

    assert optional_query(instrument, SLOW_COMMAND) == ""
    assert "clear" in instrument.events


def test_non_transport_errors_are_never_swallowed():
    class Broken:
        def query(self, command: str) -> str:
            raise ValueError("programming error, not a transport failure")

    with pytest.raises(ValueError):
        optional_query(Broken(), SLOW_COMMAND)
