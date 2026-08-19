"""Public GUI entry point.

The large Tkinter main-window implementation lives in ``main_window.py``. The
public entry point uses ``stateful_window.py`` so user preferences are loaded and
saved without changing imports such as ``from dpo4000_utils.gui.app import
ScopeGui``.
"""

from __future__ import annotations

from .stateful_window import PersistentScopeGui as ScopeGui

__all__ = ["ScopeGui", "main"]


def main() -> None:
    """Run the Tektronix DPO4000 GUI application."""
    app = ScopeGui()
    app.mainloop()


if __name__ == "__main__":
    main()
