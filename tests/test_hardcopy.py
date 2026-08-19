from dpo4000_utils.hardcopy import extract_png_bytes, strip_ieee_block_header


def test_strip_ieee_block_header():
    assert strip_ieee_block_header(b"#15abcdeTRAIL") == b"abcde"


def test_extract_png_bytes_from_prefixed_payload():
    png = b"\x89PNG\r\n\x1a\nDATAIEND\xaeB`\x82"
    assert extract_png_bytes(b"noise" + png + b"trailing") == png


def test_extract_png_bytes_from_ieee_block():
    png = b"\x89PNG\r\n\x1a\nDATAIEND\xaeB`\x82"
    payload = b"#2" + f"{len(png):02d}".encode() + png
    assert extract_png_bytes(payload) == png
