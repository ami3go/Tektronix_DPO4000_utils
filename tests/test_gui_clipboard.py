from io import BytesIO

from PIL import Image

from dpo4000_utils.gui.clipboard import image_to_dib_bytes, image_to_png_bytes


def test_image_to_dib_bytes_strips_bmp_header():
    image = Image.new("RGB", (2, 2), color="white")

    dib_bytes = image_to_dib_bytes(image)

    assert dib_bytes
    assert not dib_bytes.startswith(b"BM")

    bmp_buffer = BytesIO()
    image.save(bmp_buffer, format="BMP")
    assert dib_bytes == bmp_buffer.getvalue()[14:]


def test_image_to_png_bytes_returns_png_signature():
    image = Image.new("RGB", (2, 2), color="black")

    png_bytes = image_to_png_bytes(image)

    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
