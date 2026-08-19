"""Clipboard helpers for copying scope preview images.

Tkinter only exposes reliable text clipboard operations. Image clipboard support is
platform-specific, so this module keeps the OS-specific code isolated from the
GUI widgets.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from io import BytesIO
from pathlib import Path
import shutil
import subprocess
import sys

from PIL import Image


class ClipboardError(RuntimeError):
    """Raised when an image cannot be copied to the system clipboard."""


def image_to_png_bytes(image: Image.Image) -> bytes:
    """Return image bytes encoded as PNG."""
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def image_to_dib_bytes(image: Image.Image) -> bytes:
    """Return Windows CF_DIB bytes for a Pillow image.

    Windows clipboard image format ``CF_DIB`` expects BMP data without the
    14-byte BMP file header. Pillow can produce valid BMP bytes, so stripping
    that header gives the payload needed by ``SetClipboardData``.
    """
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="BMP")
    bmp_bytes = buffer.getvalue()
    if len(bmp_bytes) <= 14 or bmp_bytes[:2] != b"BM":
        raise ClipboardError("Could not encode image as BMP/DIB clipboard data.")
    return bmp_bytes[14:]


def copy_image_file_to_clipboard(path: str | Path) -> None:
    """Copy an image file to the system clipboard."""
    image_path = Path(path)
    if not image_path.exists():
        raise ClipboardError(f"Preview image does not exist: {image_path}")

    with Image.open(image_path) as image:
        copy_image_to_clipboard(image)


def copy_image_to_clipboard(image: Image.Image) -> None:
    """Copy a Pillow image to the system clipboard on supported platforms."""
    if sys.platform == "win32":
        _copy_image_to_windows_clipboard(image)
        return

    if sys.platform.startswith("linux"):
        _copy_image_to_linux_clipboard(image)
        return

    raise ClipboardError(
        "Image clipboard copy is not supported on this platform by this application yet."
    )


def _copy_image_to_windows_clipboard(image: Image.Image) -> None:
    """Copy image to the Windows clipboard as CF_DIB using ctypes only."""
    data = image_to_dib_bytes(image)

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = wintypes.BOOL

    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalUnlock.restype = wintypes.BOOL
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.restype = wintypes.HGLOBAL

    cf_dib = 8
    gmem_moveable = 0x0002
    h_global = None

    if not user32.OpenClipboard(None):
        raise ClipboardError("Could not open the Windows clipboard.")

    try:
        if not user32.EmptyClipboard():
            raise ClipboardError("Could not clear the Windows clipboard.")

        h_global = kernel32.GlobalAlloc(gmem_moveable, len(data))
        if not h_global:
            raise ClipboardError("Could not allocate Windows clipboard memory.")

        locked_memory = kernel32.GlobalLock(h_global)
        if not locked_memory:
            kernel32.GlobalFree(h_global)
            h_global = None
            raise ClipboardError("Could not lock Windows clipboard memory.")

        try:
            ctypes.memmove(locked_memory, data, len(data))
        finally:
            kernel32.GlobalUnlock(h_global)

        if not user32.SetClipboardData(cf_dib, h_global):
            kernel32.GlobalFree(h_global)
            h_global = None
            raise ClipboardError("Could not place image data on the Windows clipboard.")

        # The clipboard now owns the handle. Do not free it.
        h_global = None
    finally:
        user32.CloseClipboard()
        if h_global:
            kernel32.GlobalFree(h_global)


def _copy_image_to_linux_clipboard(image: Image.Image) -> None:
    """Copy image to a Linux clipboard using wl-copy or xclip if available."""
    png_bytes = image_to_png_bytes(image)

    commands = []
    if shutil.which("wl-copy"):
        commands.append(("wl-copy", "--type", "image/png"))
    if shutil.which("xclip"):
        commands.append(("xclip", "-selection", "clipboard", "-t", "image/png", "-i"))

    errors: list[str] = []
    for command in commands:
        try:
            subprocess.run(
                command,
                input=png_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            return
        except Exception as exc:
            errors.append(f"{' '.join(command)}: {exc}")

    detail = "\n".join(errors) if errors else "Install wl-clipboard or xclip."
    raise ClipboardError(f"No working Linux image clipboard command found. {detail}")


__all__ = [
    "ClipboardError",
    "copy_image_file_to_clipboard",
    "copy_image_to_clipboard",
    "image_to_dib_bytes",
    "image_to_png_bytes",
]
