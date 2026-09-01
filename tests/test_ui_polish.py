"""Final-layer presentation: concise labels, File/Scope-settings split, full-record CSV.

Replaces a source-text version. Those assertions matched strings like
'"Read acquisition setup": "Read"' in the rename table, which stays true even if
the rename never reaches a button.
"""

from __future__ import annotations

import pytest

from tests.conftest import button_texts, card_titles

pytest.importorskip("PySide6.QtWidgets")

from dpo4000_utils.gui_qt.display_window import FILE_PAGE_INDEX  # noqa: E402

ACQUISITION_PAGE_INDEX = 4
CHANNELS_PAGE_INDEX = 1
DISPLAY_PAGE_INDEX = 6


class RecordingScope:
    """Fake driver capturing the arguments the GUI passes to public API calls."""

    def __init__(self, record_length: int = 100_000) -> None:
        self.record_length = record_length
        self.calls: list[tuple] = []

    def get_record_length(self) -> int:
        self.calls.append(("get_record_length",))
        return self.record_length

    def save_all_channels_to_single_csv(self, path, **options):
        self.calls.append(("save_all_channels_to_single_csv", options))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("Time (s),CH1\n")
        return path

    def restore_default_setup(self) -> str:
        self.calls.append(("restore_default_setup",))
        return "Scope default setup restored"


@pytest.fixture
def window(make_window):
    from dpo4000_utils.gui_qt.ui_polish_window import QtScopeWindow

    win = make_window(QtScopeWindow, stub_actions=False)
    win._connection_ok = True
    win._scope = RecordingScope()
    win._run_action = lambda description, callback: callback(win._scope)
    return win


def test_file_page_offers_folder_and_open_actions(window):
    window._select_drawer_page(FILE_PAGE_INDEX)
    texts = button_texts(window)

    assert {"Folder", "Open"} <= texts
    assert "Pick folder" not in texts, "the old verbose label should be gone"


def test_scope_settings_are_a_separate_card_with_three_actions(window):
    window._select_drawer_page(FILE_PAGE_INDEX)

    titles = card_titles(window)
    assert "Scope settings" in titles
    assert "File output" in titles

    assert {"Save", "Restore", "Default"} <= button_texts(window)


@pytest.mark.parametrize(
    ("page_index", "expected", "absent"),
    [
        (
            ACQUISITION_PAGE_INDEX,
            {"Read", "Apply"},
            {"Read acquisition setup", "Apply acquisition setup"},
        ),
        (CHANNELS_PAGE_INDEX, {"Read", "Apply"}, {"Read labels", "Apply labels"}),
        (
            DISPLAY_PAGE_INDEX,
            {"Read", "Apply", "Clear"},
            {"Read display", "Apply display", "Clear text"},
        ),
    ],
)
def test_card_buttons_use_the_concise_labels(window, page_index, expected, absent):
    window._select_drawer_page(page_index)
    texts = button_texts(window)

    assert expected <= texts
    assert not (absent & texts), f"verbose labels still present: {absent & texts}"


def test_csv_export_requests_the_configured_record_length(window, tmp_path):
    window._scope.record_length = 1_000_000

    window.save_csv()

    calls = {c[0]: (c[1] if len(c) > 1 else None) for c in window._scope.calls}
    assert "get_record_length" in calls
    assert calls["save_all_channels_to_single_csv"]["point_count"] == 1_000_000, (
        "CSV must ask for the full record, not a stale transfer window"
    )


def test_csv_success_is_reported_without_a_modal(window, tmp_path):
    messages = []
    window._message = lambda *args, **kwargs: messages.append(args)

    window.save_csv()

    assert not messages, "successful save should not interrupt with a popup"
    assert "CSV saved" in window._last_action
    assert "points" in window._last_action
    assert "CSV saved" in window.statusBar().currentMessage()


def test_default_button_uses_the_public_driver_api(window):
    # The follow-up parameter refresh needs a full driver; it is not what is under test.
    refreshed = []
    window.refresh_scope_parameters = lambda *a, **k: refreshed.append(True)

    window.restore_default_scope_setup()

    assert ("restore_default_setup",) in window._scope.calls
    assert refreshed, "the GUI should re-read parameters after a factory reset"
    assert "default setup restored" in window._last_action.lower()


def test_open_folder_uses_the_platform_handler(window, monkeypatch):
    opened = []
    monkeypatch.setattr(
        "dpo4000_utils.gui_qt.ui_polish_window.QDesktopServices.openUrl",
        lambda url: opened.append(url.toLocalFile()) or True,
    )

    window.open_output_folder()

    assert opened, "Open should hand the folder to the platform file manager"
    assert "Opened folder" in window.statusBar().currentMessage()
