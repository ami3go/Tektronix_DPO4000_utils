"""Console-script entry point for the Tektronix DPO4000 GUI."""

from .app import ScopeGui


def main() -> None:
    """Run the GUI application."""
    app = ScopeGui()
    app.mainloop()
