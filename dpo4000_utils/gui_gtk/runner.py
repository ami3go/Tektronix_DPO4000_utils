"""Console-script entry point for the experimental GTK4 GUI."""

from __future__ import annotations


def main() -> None:
    """Run the experimental GTK4 GUI."""
    from .main_window import run

    raise SystemExit(run())


if __name__ == "__main__":
    main()


__all__ = ["main"]
