"""GUI configuration helpers.

This module contains GUI settings logic that can be tested without creating a
Tkinter window. The active main window still owns the Tk variables; this module
is the extraction target for filename/output settings.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

INVALID_FILENAME_CHARS = '<>:"/\\|?*'


@dataclass(frozen=True)
class FileNaming:
    """Filename options for one output type."""

    prefix: str
    base: str
    extension: str
    fallback: str
    add_timestamp: bool = True


def safe_filename_part(text: str, fallback: str = "file") -> str:
    """Return a filesystem-safe filename component for Windows/Linux."""
    value = (text or "").strip() or fallback
    cleaned = "".join("_" if ch in INVALID_FILENAME_CHARS or ord(ch) < 32 else ch for ch in value)
    cleaned = cleaned.strip(" ._")
    return cleaned or fallback


def resolve_output_folder(raw_folder: str | Path | None, *, default_name: str = "scope_gui_output") -> Path:
    """Resolve the GUI output folder to an absolute path without creating it."""
    if raw_folder is None or str(raw_folder).strip() == "":
        folder = Path.cwd() / default_name
    else:
        folder = Path(raw_folder).expanduser()
        if not folder.is_absolute():
            folder = Path.cwd() / folder
    return folder


def build_output_path(
    folder: str | Path | None,
    naming: FileNaming,
    *,
    timestamp: datetime | None = None,
) -> Path:
    """Build a complete output path from folder and naming options."""
    output_folder = resolve_output_folder(folder)
    prefix = safe_filename_part(naming.prefix, "") if naming.prefix.strip() else ""
    base = safe_filename_part(naming.base, naming.fallback)
    suffix = ""
    if naming.add_timestamp:
        suffix = "_" + (timestamp or datetime.now()).strftime("%Y%m%d_%H%M%S")
    extension = naming.extension if naming.extension.startswith(".") else f".{naming.extension}"
    return output_folder / f"{prefix}{base}{suffix}{extension}"
