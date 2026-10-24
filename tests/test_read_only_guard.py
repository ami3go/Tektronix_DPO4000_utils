"""Offline safety-contract tests for the strict read-only VISA boundary."""
import pytest

from dpo4000_utils.read_only_guard import (
    ReadOnlyViolation,
    ReadOnlyVisaSession,
    require_query,
)


class StubVISA:
    def __init__(self):
        self.sent = []
        self.timeout = 20000
        self.closed = False

    def write(self, message):
        self.sent.append(message)

    def query(self, message):
        self.sent.append(message)
        return "OK"

    def query_binary_values(self, message, **kwargs):
        self.sent.append(message)
        return [1, 2]

    def close(self):
        self.closed = True


@pytest.mark.parametrize("command", [
    "*CLS", "DATA:SOURCE CH1", "SAVE:IMAGE:FILEFORMAT PNG", "HARDCOPY START",
    "*IDN?;*CLS", "*CLS;*IDN?", "CH1:LABEL?\n*CLS", "CH1:LABEL? EXTRA",
    "", " *RST ", "CURVE?;DATA:SOURCE CH2",
])
def test_reject_unsafe_or_compound_commands_before_io(command):
    visa = StubVISA()
    safe = ReadOnlyVisaSession(visa)
    with pytest.raises(ReadOnlyViolation):
        safe.write(command)
    assert visa.sent == []
    assert safe.blocked_count == 1


def test_allow_single_query_and_binary_and_restore_visa_attributes():
    visa = StubVISA()
    safe = ReadOnlyVisaSession(visa)
    assert require_query(" *IDN? ") == "*IDN?"
    assert safe.query("*IDN?") == "OK"
    safe.write("ACQUIRE:STATE?")
    assert safe.query_binary_values("CURVE?", datatype="h") == [1, 2]
    safe.timeout = 1000
    assert visa.timeout == 1000
    assert visa.sent == ["*IDN?", "ACQUIRE:STATE?", "CURVE?"]
    assert safe.query_count == 3
    safe.close()
    assert visa.closed


def test_direct_transport_bypass_is_disallowed():
    visa = StubVISA()
    safe = ReadOnlyVisaSession(visa)
    with pytest.raises(ReadOnlyViolation):
        safe.write_raw(b"*RST\n")
    with pytest.raises(ReadOnlyViolation):
        safe.write_binary_values("DATA:SOURCE", [1])
    with pytest.raises(ReadOnlyViolation):
        safe.clear()
    with pytest.raises(ReadOnlyViolation):
        _ = safe.visalib
    assert visa.sent == []
    assert safe.blocked_count == 3
