"""The control pages present the widgets and choices their cards promise.

Replaces source-text assertions such as `'"HIRES"' in content`, which stayed true
whether or not the value ever reached a combo box.
"""

from __future__ import annotations

import pytest

from tests.conftest import button_texts, card_titles

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtGui import QKeySequence  # noqa: E402
from PySide6.QtWidgets import QComboBox, QTableWidget  # noqa: E402

from dpo4000_utils.control import (  # noqa: E402
    ACQUISITION_MODES,
    AVERAGE_COUNTS,
    RECORD_LENGTH_LABELS,
)

CHANNELS_PAGE_INDEX = 1
MEASUREMENT_PAGE_INDEX = 2
ACQUISITION_PAGE_INDEX = 4


def _combo_items(combo: QComboBox) -> list[str]:
    return [combo.itemText(i) for i in range(combo.count())]


# ----------------------------------------------------------------------
# Acquisition
# ----------------------------------------------------------------------
def test_acquisition_page_offers_the_documented_modes(make_window):
    window = make_window()
    window._select_drawer_page(ACQUISITION_PAGE_INDEX)

    items = _combo_items(window.acquisition_mode)
    assert set(items) == set(ACQUISITION_MODES)
    assert "HIRES" in items
    assert "AVERAGE" in items


def test_acquisition_page_offers_the_documented_average_counts(make_window):
    window = make_window()
    window._select_drawer_page(ACQUISITION_PAGE_INDEX)

    assert _combo_items(window.acquisition_average_count) == list(AVERAGE_COUNTS)


def test_acquisition_page_offers_the_documented_record_lengths(make_window):
    window = make_window()
    window._select_drawer_page(ACQUISITION_PAGE_INDEX)

    assert _combo_items(window.acquisition_record_length) == list(RECORD_LENGTH_LABELS)


def test_average_count_is_only_enabled_in_average_mode(make_window):
    window = make_window()
    window._select_drawer_page(ACQUISITION_PAGE_INDEX)

    window.acquisition_mode.setCurrentText("AVERAGE")
    window._update_average_count_enabled()
    assert window.acquisition_average_count.isEnabled()

    window.acquisition_mode.setCurrentText("SAMPLE")
    window._update_average_count_enabled()
    assert not window.acquisition_average_count.isEnabled()


# ----------------------------------------------------------------------
# Measurement
# ----------------------------------------------------------------------
def test_measurement_page_keeps_the_existing_measurement_manager(make_window):
    window = make_window()
    window._select_drawer_page(MEASUREMENT_PAGE_INDEX)

    assert "Existing scope measurements" in card_titles(window)

    tables = [t for t in window.findChildren(QTableWidget) if t.objectName() == "ExistingMeasurementsTable"]
    assert tables, "the existing-measurements table is missing"

    assert {"Read configured", "Load selected", "Apply edit", "Delete selected"} <= button_texts(window)


def test_measurement_editor_can_be_populated_from_a_row(make_window):
    window = make_window()
    window._select_drawer_page(MEASUREMENT_PAGE_INDEX)

    window._set_measurement_editor(slot=3, measurement_type="FREQUENCY", source1="CH2", source2="")

    assert window.measurement_slot.currentText() == "3"
    assert window.measurement_type.currentText() == "FREQUENCY"
    assert window.measurement_source1.currentText() == "CH2"


# ----------------------------------------------------------------------
# Channels and MATH
# ----------------------------------------------------------------------
def test_channels_page_has_full_channel_and_math_configuration_cards(make_window):
    window = make_window()
    window._select_drawer_page(CHANNELS_PAGE_INDEX)

    titles = card_titles(window)
    assert "Full channel configuration" in titles
    assert "Math channel configuration" in titles

    assert _combo_items(window.channel_config_channel) == ["1", "2", "3", "4"]

    for attribute in (
        "channel_config_display",
        "channel_config_scale",
        "channel_config_position",
        "channel_config_offset",
        "channel_config_coupling",
        "channel_config_bandwidth",
        "channel_config_invert",
        "channel_config_probe_gain",
        "math_config_display",
        "math_config_define",
        "math_config_scale",
        "math_config_position",
    ):
        assert hasattr(window, attribute), f"missing configuration widget {attribute}"


def test_channel_and_math_actions_are_reachable(make_window):
    window = make_window()
    window._select_drawer_page(CHANNELS_PAGE_INDEX)

    for handler in (
        "read_channel_configuration",
        "apply_channel_configuration",
        "read_math_configuration",
        "apply_math_configuration",
    ):
        assert callable(getattr(window, handler))


# ----------------------------------------------------------------------
# Preview
# ----------------------------------------------------------------------
def test_preview_supports_copy_shortcut(make_window):
    window = make_window()

    assert hasattr(window, "preview_copy_shortcut")
    assert window.preview_copy_shortcut.key() == QKeySequence(QKeySequence.StandardKey.Copy)
