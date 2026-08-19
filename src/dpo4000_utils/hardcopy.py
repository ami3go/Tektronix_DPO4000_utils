"""Screen hardcopy capture helpers."""

from __future__ import annotations

from pathlib import Path


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PNG_IEND = b"IEND\xaeB`\x82"


def strip_ieee_block_header(payload: bytes) -> bytes:
    """Strip an IEEE 488.2 definite-length block header if one is present."""
    if not payload.startswith(b"#") or len(payload) < 2:
        return payload

    try:
        digit_count = int(payload[1:2])
    except ValueError:
        return payload

    if digit_count <= 0:
        return payload

    header_end = 2 + digit_count
    if len(payload) < header_end:
        return payload

    try:
        data_length = int(payload[2:header_end])
    except ValueError:
        return payload

    data_end = header_end + data_length
    if len(payload) >= data_end:
        return payload[header_end:data_end]

    return payload[header_end:]


def extract_png_bytes(payload: bytes) -> bytes:
    """Extract a clean PNG stream from Tektronix hardcopy response bytes."""
    payload = strip_ieee_block_header(payload)

    start = payload.find(PNG_SIGNATURE)
    if start < 0:
        return payload

    png = payload[start:]
    iend = png.find(PNG_IEND)
    if iend >= 0:
        png = png[: iend + len(PNG_IEND)]
    return png


class HardcopyMixin:
    """Mixin for screen image capture."""

    def read_screen_png(self) -> bytes:
        """Capture current oscilloscope screen and return PNG bytes."""
        scope = self.ensure_connected()
        scope.write("SAVe:IMAGe:FILEFormat PNG")
        scope.write("SAVe:IMAGe:INKSaver OFF")
        scope.write("HARDCopy STARt")
        return extract_png_bytes(scope.read_raw())

    def save_image_path(self, path=""):
        """Save current oscilloscope screen as a PNG file."""
        img_data = self.read_screen_png()
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(img_data)
