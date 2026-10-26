from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from dpo4000_utils.gui_qt.composition import legacy_surface  # noqa: E402
from dpo4000_utils.gui_qt.composition.window import QtScopeWindow  # noqa: E402


class _SettingsSession:
    """Raw VISA-session stand-in: the real driver reaches ``query`` only through this."""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def query(self, command: str) -> str:
        self.queries.append(command)
        return {"*IDN?": "TEKTRONIX,DPO4054,C000000,v2.68", "*LRN?": ":HEADER 0;:ACQUIRE:STATE 0"}[command]


class _SettingsScope:
    """Shaped like the real DPO4054 driver: no ``query`` of its own."""

    def __init__(self) -> None:
        self.session = _SettingsSession()

    @property
    def queries(self) -> list[str]:
        return self.session.queries

    def ensure_connected(self) -> _SettingsSession:
        return self.session


@pytest.fixture
def surface(monkeypatch):
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([sys.executable, "automation-hook-test"])
    window = QtScopeWindow()
    surface = window.feature_surface
    scope = _SettingsScope()
    loaded: list[Path] = []
    actions: list[str] = []

    def run_action(description, callback, *, on_success=None, on_error=None, retain_session=False):
        actions.append(description)
        try:
            result = callback(scope)
        except Exception as exc:  # pragma: no cover - surfaced through assertions
            if on_error is not None:
                on_error(exc)
        else:
            if on_success is not None:
                on_success(result)

    monkeypatch.setattr(surface, "_run_action", run_action)
    monkeypatch.setattr(surface, "_load_preview", loaded.append)
    clock = [100.0]
    monkeypatch.setattr(legacy_surface.time, "monotonic", lambda: clock[0])
    card = surface._build_automation_output_card()  # keep a reference: the card owns the checkboxes
    surface.test_scope, surface.test_loaded, surface.test_actions, surface.test_clock = scope, loaded, actions, clock
    try:
        yield surface
    finally:
        card.deleteLater()
        window.close()
        window.deleteLater()
        app.processEvents()


def test_output_card_offers_both_options_with_safe_defaults(surface) -> None:
    assert surface.automation_preview_refresh_check.isChecked() is True
    assert surface.automation_settings_json_check.isChecked() is False


def test_automation_png_refreshes_preview_throttled(surface, tmp_path: Path) -> None:
    surface._automation_last_path = tmp_path / "evt_0001.png"
    surface._automation_last_path = tmp_path / "evt_0002.png"  # within 0.5 s: skipped
    surface.test_clock[0] += 0.6
    surface._automation_last_path = tmp_path / "evt_0003.png"
    surface._automation_last_path = tmp_path / "evt_0003.csv"  # CSV never loads a preview
    assert surface.test_loaded == [tmp_path / "evt_0001.png", tmp_path / "evt_0003.png"]
    assert surface._automation_last_path == tmp_path / "evt_0003.csv"
    assert surface.test_actions == []  # settings JSON is off by default


def test_preview_refresh_can_be_disabled(surface, tmp_path: Path) -> None:
    surface.automation_preview_refresh_check.setChecked(False)
    surface._automation_last_path = tmp_path / "evt_0001.png"
    assert surface.test_loaded == []


def test_settings_json_saved_once_per_event_next_to_artifacts(surface, tmp_path: Path) -> None:
    surface.automation_settings_json_check.setChecked(True)
    surface._automation_last_path = tmp_path / "evt_0001.png"
    surface._automation_last_path = tmp_path / "evt_0001.csv"  # same event: no second save
    surface._automation_last_path = tmp_path / "evt_0002.csv"

    assert surface.test_actions == ["Saving automation scope settings"] * 2
    first = json.loads((tmp_path / "evt_0001.settings.json").read_text(encoding="utf-8"))
    assert first["setup"] == ":HEADER 0;:ACQUIRE:STATE 0"
    assert first["instrument"].startswith("TEKTRONIX,DPO4054")
    assert (tmp_path / "evt_0002.settings.json").is_file()
    # Read-only queries only.
    assert set(surface.test_scope.queries) <= {"*IDN?", "*LRN?"}


def test_clearing_last_path_is_a_no_op(surface) -> None:
    surface.automation_settings_json_check.setChecked(True)
    surface._automation_last_path = None
    assert surface._automation_last_path is None
    assert surface.test_actions == [] and surface.test_loaded == []


def test_settings_path_helper() -> None:
    assert legacy_surface.automation_settings_path(Path("/x/run_007.png")) == Path("/x/run_007.settings.json")


def test_destroyed_option_widgets_fall_back_to_defaults(surface, tmp_path: Path) -> None:
    import shiboken6

    shiboken6.delete(surface.automation_preview_refresh_check)
    shiboken6.delete(surface.automation_settings_json_check)
    surface._automation_last_path = tmp_path / "evt_0001.png"
    assert surface.test_loaded == [tmp_path / "evt_0001.png"]  # default on
    assert surface.test_actions == []  # default off
