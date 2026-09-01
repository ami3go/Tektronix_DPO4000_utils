"""Validation helpers for values embedded in SCPI program messages."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

_SCPI_MESSAGE_SEPARATORS = (";", "\r", "\n", "\x00")


def ensure_single_scpi_value(value: Any, *, field: str, allow_empty: bool = False) -> str:
    """Return stripped text that cannot terminate/start another SCPI message."""
    text = str(value if value is not None else "").strip()
    if not text and not allow_empty:
        raise ValueError(f"{field} cannot be empty.")
    if any(separator in text for separator in _SCPI_MESSAGE_SEPARATORS):
        raise ValueError(
            f"{field} contains an invalid SCPI message separator. "
            "Semicolons and line breaks are not allowed in this field."
        )
    return text


def quote_scpi_string(value: Any, *, max_length: int | None = None) -> str:
    """Return a single-line quoted SCPI string safe from message termination.

    SCPI separators inside a quoted string are data, not program separators, but
    physical CR/LF/NUL bytes are normalized away and embedded double quotes are
    replaced so user text cannot terminate the string early.
    """
    clean = " ".join(str(value if value is not None else "").replace("\x00", " ").splitlines())
    clean = clean.replace('"', "'").strip()
    if max_length is not None:
        clean = clean[: int(max_length)]
    return f'"{clean}"'


def format_scpi_number(
    value: Any,
    *,
    field: str,
    positive: bool = False,
    nonnegative: bool = False,
    integer: bool = False,
) -> str:
    """Parse and deterministically format one finite SCPI numeric argument."""
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric, not boolean.")
    text = ensure_single_scpi_value(value, field=field)
    try:
        number = float(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a numeric value.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite (NaN/Inf are not allowed).")
    if positive and number <= 0:
        raise ValueError(f"{field} must be greater than zero.")
    if nonnegative and number < 0:
        raise ValueError(f"{field} must be zero or greater.")
    if integer:
        if not number.is_integer():
            raise ValueError(f"{field} must be an integer.")
        return str(int(number))
    return f"{number:g}"


def normalize_scpi_token(value: Any, *, field: str, uppercase: bool = True) -> str:
    """Validate one unquoted SCPI token/value while preserving safe punctuation."""
    text = ensure_single_scpi_value(value, field=field)
    return text.upper() if uppercase else text


def normalize_scpi_enum(
    value: Any,
    allowed: Sequence[str],
    *,
    field: str,
    aliases: Mapping[str, str] | None = None,
) -> str:
    """Normalize an enum token and require it to be in the documented set."""
    token = normalize_scpi_token(value, field=field, uppercase=True)
    compact = token.replace("-", "").replace("_", "").replace(" ", "")
    alias_map = {
        str(key).upper().replace("-", "").replace("_", "").replace(" ", ""): str(val).upper()
        for key, val in (aliases or {}).items()
    }
    if compact in alias_map:
        token = alias_map[compact]
    allowed_map = {
        str(item).upper().replace("-", "").replace("_", "").replace(" ", ""): str(item).upper()
        for item in allowed
    }
    normalized_key = token.replace("-", "").replace("_", "").replace(" ", "")
    if normalized_key not in allowed_map:
        raise ValueError(f"Unsupported {field.lower()}: {value!r}.")
    return allowed_map[normalized_key]


__all__ = [
    "ensure_single_scpi_value",
    "format_scpi_number",
    "normalize_scpi_enum",
    "normalize_scpi_token",
    "quote_scpi_string",
]
