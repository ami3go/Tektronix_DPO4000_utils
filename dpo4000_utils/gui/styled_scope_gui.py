"""Public styled GUI class."""

from __future__ import annotations

from .scope_gui import ScopeGui as BaseScopeGui
from .style import apply_readable_combobox_style


class ScopeGui(BaseScopeGui):
    """Scope GUI with platform-safe combobox colors applied."""

    def _build_style(self) -> None:
        super()._build_style()
        apply_readable_combobox_style(self)


__all__ = ["ScopeGui"]
