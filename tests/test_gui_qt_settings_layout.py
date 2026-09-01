"""File-page naming fields are full-width and stacked, not squeezed into a column.

Replaces assertions like `"prefix.setMinimumWidth(180)" in content` and
`"setMaximumWidth(105)" not in content`, which described the call rather than the
resulting widget.
"""

from __future__ import annotations

import pytest

from tests.conftest import file_page_index

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QLineEdit, QSizePolicy  # noqa: E402

NAMING_WIDGETS = (
    "png_prefix",
    "png_base",
    "csv_prefix",
    "csv_base",
    "settings_prefix",
    "settings_base",
)
TIMESTAMP_WIDGETS = ("png_timestamp", "csv_timestamp", "settings_timestamp")


@pytest.fixture
def file_page(make_window):
    window = make_window()
    window._select_drawer_page(file_page_index())
    return window


def test_file_page_exposes_every_preference_widget(file_page):
    for name in (*NAMING_WIDGETS, *TIMESTAMP_WIDGETS, "output_folder", "restore_wait_opc"):
        assert hasattr(file_page, name), f"missing preference widget {name}"


def test_naming_fields_expand_rather_than_being_capped(file_page):
    for name in NAMING_WIDGETS:
        field: QLineEdit = getattr(file_page, name)
        assert field.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding, (
            f"{name} does not expand to fill the row"
        )
        assert field.maximumWidth() > 105, f"{name} is still width-capped at {field.maximumWidth()}"


def test_naming_fields_have_room_to_read_their_contents(file_page):
    for name in NAMING_WIDGETS:
        field: QLineEdit = getattr(file_page, name)
        assert field.minimumWidth() >= 180, (
            f"{name} minimum width is {field.minimumWidth()}, too narrow to read"
        )


def test_output_folder_row_is_wide(file_page):
    assert file_page.output_folder.minimumWidth() >= 240
    assert file_page.output_folder.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding


def test_each_output_kind_has_its_own_naming_block(file_page):
    blocks = file_page.findChildren(object, "SettingsNamingBlock")
    assert len(blocks) >= 3, "expected a naming block for PNG, CSV and settings JSON"


def test_naming_choices_drive_the_generated_filename(file_page):
    file_page.png_prefix.setText("lab_")
    file_page.png_base.setText("screen")
    file_page.png_timestamp.setChecked(False)

    path = file_page._build_output_path("png")

    assert path.name == "lab_screen.png"


def test_timestamp_checkbox_adds_a_stamp_to_the_filename(file_page):
    file_page.csv_prefix.setText("run_")
    file_page.csv_base.setText("wave")
    file_page.csv_timestamp.setChecked(True)

    path = file_page._build_output_path("csv")

    assert path.name.startswith("run_wave_")
    assert path.suffix == ".csv"
    assert len(path.stem) > len("run_wave_")
