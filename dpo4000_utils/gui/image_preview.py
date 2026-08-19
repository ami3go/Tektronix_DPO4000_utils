"""Image preview helpers for the Tkinter GUI.

The functions here are deliberately GUI-toolkit-light so they can be tested
without creating a Tk window. The current main window can migrate to these
helpers incrementally.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class PreviewSize:
    """A bounded preview size in pixels."""

    width: int
    height: int


def usable_preview_size(
    widget_width: int,
    widget_height: int,
    *,
    fallback_width: int = 820,
    fallback_height: int = 500,
    margin: int = 12,
    min_width: int = 120,
    min_height: int = 90,
) -> PreviewSize:
    """Return a useful preview canvas size from raw widget dimensions."""
    width = widget_width if widget_width > 10 else fallback_width
    height = widget_height if widget_height > 10 else fallback_height
    return PreviewSize(max(min_width, width - margin), max(min_height, height - margin))


def subsample_factor(image_width: int, image_height: int, max_width: int, max_height: int) -> int:
    """Return the integer Tk PhotoImage subsample factor needed to fit an image."""
    if image_width <= 0 or image_height <= 0:
        raise ValueError("Image dimensions must be positive.")
    if max_width <= 0 or max_height <= 0:
        raise ValueError("Maximum preview dimensions must be positive.")
    scale = max(image_width / max_width, image_height / max_height, 1)
    return max(1, math.ceil(scale))
