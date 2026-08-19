"""Public GUI entry point.

The large Tkinter main-window implementation lives in ``main_window.py``.
Keeping this module small makes the package entry point easier to maintain while
preserving existing imports such as ``from dpo4000_utils.gui.app import ScopeGui``.
"""

from __future__ import annotations

from .main_window import ScopeGui

__all__ = ["ScopeGui", "main"]


def main() -> None:
    """Run the Tektronix DPO4000 GUI application."""
    app = ScopeGui()
    app.mainloop()


if __name__ == "__main__":
    main()
