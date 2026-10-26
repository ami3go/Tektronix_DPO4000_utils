from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFileDialog  # noqa: E402

from dpo4000_utils.evidence import verify_evidence_bundle  # noqa: E402
from dpo4000_utils.recipe import (  # noqa: E402
    Recipe,
    RecipeResult,
    RecipeRunState,
    RecipeStep,
    StepResult,
    recipe_to_mapping,
)
from dpo4000_utils.rules import CompareOperator, RuleSet, ScalarRule, rule_set_to_mapping  # noqa: E402


class _FakeSession:
    """Raw VISA session stand-in; the real driver reaches ``query`` only through this."""

    def query(self, command: str) -> str:
        assert command == "*LRN?"
        return ":HEADER 0;:ACQUIRE:STATE 0"


class _FakeScope:
    """Shaped like the real DPO4054 driver: no ``query`` of its own."""

    resource_name = "TCPIP0::192.0.2.7::inst0::INSTR"

    def query_identity(self) -> str:
        return "TEKTRONIX,DPO4054,C000000,CF:91.1CT FV:v2.68"

    def read_screen_png(self) -> bytes:
        raise AssertionError("screen capture is disabled in this test")

    def read_enabled_waveforms(self, *, point_count):
        raise AssertionError("waveform capture is disabled in this test")

    def ensure_connected(self) -> _FakeSession:
        return _FakeSession()


def _synchronous_run_action(label, execute, *, on_success, on_error, retain_session=False):
    try:
        result = execute(_FakeScope())
    except Exception as exc:  # pragma: no cover - surfaced through assertion below
        on_error(exc)
    else:
        on_success(result)


def _recipe() -> Recipe:
    return Recipe("GUI evidence", (RecipeStep.call("get_measurement_value", 1, name="MEAS1"),))


def _rules() -> RuleSet:
    return RuleSet("5 V", ScalarRule("vmin", "MEAS1", CompareOperator.GTE, value=4.95))


def _result() -> RecipeResult:
    return RecipeResult(
        "GUI evidence",
        RecipeRunState.COMPLETED,
        1.0,
        1.5,
        (StepResult(0, "MEAS1", 1, 1.0, 1.1, 5.01),),
    )


def test_recipe_page_hands_definitions_to_evidence_panel_after_run() -> None:
    app = QApplication.instance() or QApplication([])
    from dpo4000_utils.gui_qt.composition.pages.evidence import RecipeEvidencePage

    page = RecipeEvidencePage(run_action=_synchronous_run_action)
    page._active_recipe = _recipe()
    page._active_rule_set = _rules()
    page._run_finished(_result())

    panel = page.evidence_panel
    assert panel._recipe == _recipe()
    assert panel._rule_set == _rules()
    assert panel._rule_result is not None
    assert panel.save_button.isEnabled()
    page.deleteLater()
    app.processEvents()


def test_evidence_panel_writes_definitions_setup_and_transport(tmp_path: Path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    from dpo4000_utils.gui_qt.composition.pages.evidence import EvidenceBundlePanel

    target = tmp_path / "gui.dpoe"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target), ""))
    panel = EvidenceBundlePanel(run_action=_synchronous_run_action)
    panel.screen_checkbox.setChecked(False)
    panel.waveform_checkbox.setChecked(False)
    panel.set_result(_result(), None, recipe=_recipe(), rule_set=_rules())

    panel._save_clicked()

    assert panel.status_label.text().startswith("Saved "), panel.status_label.text()
    manifest = verify_evidence_bundle(target).manifest
    assert manifest["transport"] == "TCPIP"
    with ZipFile(target) as archive:
        assert json.loads(archive.read("definitions/recipe.json")) == recipe_to_mapping(_recipe())
        assert json.loads(archive.read("definitions/rules.json")) == rule_set_to_mapping(_rules())
        assert archive.read("setup/after.txt") == b":HEADER 0;:ACQUIRE:STATE 0"
        assert "setup/before.txt" not in archive.namelist()
        for name in archive.namelist():
            assert b"192.0.2.7" not in archive.read(name)
    panel.deleteLater()
    app.processEvents()


def test_disabling_setup_capture_skips_lrn_query(tmp_path: Path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    from dpo4000_utils.gui_qt.composition.pages.evidence import EvidenceBundlePanel

    class _NoQueryScope(_FakeScope):
        def ensure_connected(self):
            raise AssertionError("setup must not be queried when disabled")

    def run_action(label, execute, *, on_success, on_error, retain_session=False):
        on_success(execute(_NoQueryScope()))

    target = tmp_path / "nosetup.dpoe"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(target), ""))
    panel = EvidenceBundlePanel(run_action=run_action)
    panel.screen_checkbox.setChecked(False)
    panel.waveform_checkbox.setChecked(False)
    panel.setup_checkbox.setChecked(False)
    panel.set_result(_result())

    panel._save_clicked()

    with ZipFile(target) as archive:
        names = archive.namelist()
    assert "setup/after.txt" not in names
    assert "definitions/recipe.json" not in names
    panel.deleteLater()
    app.processEvents()
