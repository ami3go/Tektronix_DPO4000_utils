"""Public GUI entry point.

The large Tkinter main-window implementation lives in ``main_window.py``. The
public entry point layers small wrappers on top of it so preferences, shared
CSV/export helpers, and extracted tab builders are used without changing imports
such as ``from dpo4000_utils.gui.app import ScopeGui``.
"""

from __future__ import annotations

from .sectioned_window import SectionedScopeGui as ScopeGui

__all__ = ["ScopeGui", "main"]


def main() -> None:
    """Run the Tektronix DPO4000 GUI application."""
    app = ScopeGui()
    app.mainloop()


if __name__ == "__main__":
    main()
