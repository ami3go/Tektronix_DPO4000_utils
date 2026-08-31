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
    def __init__(self, payload: bytes, *, image_file_format: str = "BMP"):
        self.payload = payload
        self.commands = []
        self.timeout = 1000
        self.read_termination = "\n"
        self.write_termination = None
        self.image_file_format = image_file_format

    def query(self, command: str) -> str:
        self.commands.append(("query", command))
        if command == "SAVE:IMAGE:FILEFORMAT?":
            return self.image_file_format
        raise AssertionError(command)

    def write(self, command: str) -> None:
        self.commands.append(("write", command))

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


def test_capture_screen_png_validates_and_restores_session_and_scope_format():
    inst = FakeInstrument(b"prefix" + PNG + b"trailing", image_file_format="BMP")

    assert capture_screen_png(inst, command_delay_s=0) == PNG

    queries = [command for kind, command in inst.commands if kind == "query"]
    writes = [command for kind, command in inst.commands if kind == "write"]
    assert queries == ["SAVE:IMAGE:FILEFORMAT?"]
    assert writes == [
        "SAVE:IMAGE:FILEFORMAT PNG",
        "HARDCOPY START",
        "SAVE:IMAGE:FILEFORMAT BMP",
    ]
    assert "*CLS" not in writes
    assert all(not command.startswith("HEADER") for command in writes)
    assert all(not command.startswith("VERBOSE") for command in writes)
    assert all(not command.startswith("HARDCOPY:FORMAT") for command in writes)
    assert inst.timeout == 1000
    assert inst.read_termination == "\n"
    assert inst.write_termination is None


def test_capture_failure_still_restores_image_format_and_session_attributes():
    inst = FakeInstrument(b"not png", image_file_format="BMP")

    with pytest.raises(HardcopyCaptureError):
        capture_screen_png(inst, command_delay_s=0)

    writes = [command for kind, command in inst.commands if kind == "write"]
    assert writes[-1] == "SAVE:IMAGE:FILEFORMAT BMP"
    assert inst.timeout == 1000
    assert inst.read_termination == "\n"
    assert inst.write_termination is None
