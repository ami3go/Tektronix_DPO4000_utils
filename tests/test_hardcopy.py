import pytest

from dpo4000_utils.hardcopy import (
    HardcopyCaptureError,
    capture_screen_png,
    extract_png_bytes,
    require_png_bytes,
    strip_ieee_block_header,
    trim_png_after_iend,
)


PNG = b"\x89PNG\r\n\x1a\nDATAIEND\xaeB`\x82"


class FakeInstrument:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.commands = []
        self.timeout = 1000
        self.read_termination = "\n"
        self.write_termination = None

    def write(self, command: str) -> None:
        self.commands.append(command)

    def read_raw(self) -> bytes:
        return self.payload


def test_strip_ieee_block_header():
    assert strip_ieee_block_header(b"#15abcdeTRAIL") == b"abcde"


def test_extract_png_bytes_from_prefixed_payload():
    assert extract_png_bytes(b"noise" + PNG + b"trailing") == PNG


def test_extract_png_bytes_from_ieee_block():
    payload = b"#2" + f"{len(PNG):02d}".encode() + PNG
    assert extract_png_bytes(payload) == PNG


def test_trim_png_after_iend():
    assert trim_png_after_iend(PNG + b"trailing") == PNG


def test_require_png_bytes_raises_with_diagnostic_prefix():
    with pytest.raises(HardcopyCaptureError, match="No PNG signature"):
        require_png_bytes(b"not a png response")


def test_capture_screen_png_validates_and_restores_session_settings():
    inst = FakeInstrument(b"prefix" + PNG + b"trailing")

    assert capture_screen_png(inst, command_delay_s=0) == PNG
    assert "HARDCOPY START" in inst.commands
    assert inst.timeout == 1000
    assert inst.read_termination == "\n"
    assert inst.write_termination is None
