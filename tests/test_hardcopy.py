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
STREAMING_PNG = b"\x89PNG\r\n\x1a\n\x00\x00\x00\x00IEND\xaeB`\x82"


class FakeInstrument:
    def __init__(self, payload: bytes, *, image_format: str = "BMP"):
        self.payload = payload
        self.commands = []
        self.timeout = 1000
        self.read_termination = "\n"
        self.write_termination = None
        self.image_format = image_format

    def query(self, command: str) -> str:
        self.commands.append(("query", command))
        if command == "SAVE:IMAGE:FILEFORMAT?":
            return self.image_format
        raise AssertionError(command)

    def write(self, command: str) -> None:
        self.commands.append(("write", command))

    def read_raw(self) -> bytes:
        return self.payload


class ExactReadInstrument(FakeInstrument):
    """Model a backend where open-ended read_raw would wait for EOM forever."""

    def __init__(self, stream: bytes, *, image_format: str = "BMP"):
        super().__init__(b"", image_format=image_format)
        self.stream = stream
        self.offset = 0
        self.read_requests: list[int] = []
        self.read_raw_called = False

    def read_bytes(self, count: int, *, break_on_termchar: bool = False) -> bytes:
        assert break_on_termchar is False
        self.read_requests.append(count)
        end = self.offset + count
        if end > len(self.stream):
            raise AssertionError(
                f"Reader requested bytes past supplied stream: {self.offset}+{count}"
            )
        data = self.stream[self.offset:end]
        self.offset = end
        return data

    def read_raw(self) -> bytes:
        self.read_raw_called = True
        raise AssertionError("open-ended read_raw must not be used when read_bytes exists")


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


def test_capture_screen_png_uses_documented_image_format_and_restores_session():
    inst = FakeInstrument(b"prefix" + PNG + b"trailing", image_format="BMP")

    assert capture_screen_png(inst, command_delay_s=0) == PNG

    assert inst.commands[0] == ("query", "SAVE:IMAGE:FILEFORMAT?")
    writes = [command for kind, command in inst.commands if kind == "write"]
    assert writes == [
        "SAVE:IMAGE:FILEFORMAT PNG",
        "HARDCOPY START",
        "SAVE:IMAGE:FILEFORMAT BMP",
    ]
    assert all("HARDCOPY:FORMAT" not in command for _, command in inst.commands)
    assert "*CLS" not in writes
    assert all(not command.startswith("HEADER") for command in writes)
    assert all(not command.startswith("VERBOSE") for command in writes)
    assert inst.timeout == 1000
    assert inst.read_termination == "\n"
    assert inst.write_termination is None


def test_capture_uses_exact_png_chunk_reads_and_stops_at_iend():
    trailing = b"bytes-that-must-not-be-read"
    inst = ExactReadInstrument(STREAMING_PNG + trailing)

    assert capture_screen_png(inst, command_delay_s=0) == STREAMING_PNG

    assert inst.read_raw_called is False
    assert inst.offset == len(STREAMING_PNG)
    assert sum(inst.read_requests) == len(STREAMING_PNG)
    assert inst.stream[inst.offset:] == trailing


def test_capture_uses_ieee_definite_length_without_waiting_for_eom():
    length_text = str(len(STREAMING_PNG)).encode("ascii")
    header = b"#" + str(len(length_text)).encode("ascii") + length_text
    trailing = b"bytes-after-ieee-block"
    inst = ExactReadInstrument(header + STREAMING_PNG + trailing)

    assert capture_screen_png(inst, command_delay_s=0) == STREAMING_PNG

    assert inst.read_raw_called is False
    assert inst.offset == len(header) + len(STREAMING_PNG)
    assert inst.stream[inst.offset:] == trailing


def test_capture_failure_still_restores_image_format_and_session_attributes():
    inst = FakeInstrument(b"not png", image_format="BMP")

    with pytest.raises(HardcopyCaptureError):
        capture_screen_png(inst, command_delay_s=0)

    writes = [command for kind, command in inst.commands if kind == "write"]
    assert writes[-1] == "SAVE:IMAGE:FILEFORMAT BMP"
    assert inst.timeout == 1000
    assert inst.read_termination == "\n"
    assert inst.write_termination is None
