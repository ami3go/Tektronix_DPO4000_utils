"""Public GUI entry point.

The public entry point imports the flattened ``scope_gui.ScopeGui`` class. That
class owns the active GUI behavior while preserving imports such as
``from dpo4000_utils.gui.app import ScopeGui``.
"""

from __future__ import annotations

from .scope_gui import ScopeGui

__all__ = ["ScopeGui", "main"]


def main() -> None:
    """Run the Tektronix DPO4000 GUI application."""
    app = ScopeGui()
    app.mainloop()


if __name__ == "__main__":
    main()
