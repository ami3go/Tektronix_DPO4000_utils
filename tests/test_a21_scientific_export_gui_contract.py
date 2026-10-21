from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PANEL = (
    ROOT
    / "dpo4000_utils"
    / "gui_qt"
    / "composition"
    / "pages"
    / "scientific_export.py"
)
LEGACY_SURFACE = ROOT / "dpo4000_utils" / "gui_qt" / "composition" / "legacy_surface.py"


def test_a21_panel_uses_worker_public_api_and_no_raw_transport() -> None:
    text = PANEL.read_text(encoding="utf-8")
    assert "scope.read_enabled_waveforms" in text
    assert "export_scientific_dataset" in text
    assert "self._run_action(" in text
    assert "retain_session=True" in text
    for forbidden in (".scope", ".query(", ".write(", "ResourceManager("):
        assert forbidden not in text


def test_a21_panel_exposes_expected_controls_and_scaling_sizes() -> None:
    text = PANEL.read_text(encoding="utf-8")
    for object_name in (
        "scientificExportPanel",
        "scientificExportFormat",
        "scientificExportPoints",
        "scientificExportCompressed",
        "scientificExportButton",
        "scientificExportStatus",
    ):
        assert object_name in text
    for count in ("1_000", "10_000", "100_000", "1_000_000"):
        assert count in text
    assert "ScientificFormat.NPZ" in text
    assert "ScientificFormat.DPOZ" in text


def test_a21_extends_existing_file_page_instead_of_replacing_it() -> None:
    text = LEGACY_SURFACE.read_text(encoding="utf-8")
    assert "page = super()._build_file_tab()" in text
    assert "attach_scientific_export_panel(self, page)" in text
