from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GUI_FILES = (
    "main_window.py",
    "acquisition_window.py",
    "measurement_window.py",
    "display_window.py",
)
FORBIDDEN_INSTRUMENT_PATTERNS = (
    "scope.scope",
    'getattr(scope, "scope"',
    ".query(",
    ".write(",
)


def test_legacy_active_qt_layers_use_public_driver_api_only() -> None:
    for filename in GUI_FILES:
        source = (ROOT / "dpo4000_utils" / "gui_qt" / filename).read_text(encoding="utf-8")
        for pattern in FORBIDDEN_INSTRUMENT_PATTERNS:
            assert pattern not in source, f"{filename} contains raw instrument access: {pattern}"


def test_legacy_qt_layers_do_not_own_scpi_query_maps() -> None:
    acquisition = (ROOT / "dpo4000_utils" / "gui_qt" / "acquisition_window.py").read_text(
        encoding="utf-8"
    )
    measurement = (ROOT / "dpo4000_utils" / "gui_qt" / "measurement_window.py").read_text(
        encoding="utf-8"
    )
    display = (ROOT / "dpo4000_utils" / "gui_qt" / "display_window.py").read_text(
        encoding="utf-8"
    )
    assert "ACQUISITION_SETUP_QUERIES" not in acquisition
    assert "MEASUREMENT_SETUP_QUERIES" not in measurement
    assert "DISPLAY_SETUP_QUERIES" not in display
