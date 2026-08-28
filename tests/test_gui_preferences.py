from __future__ import annotations

import json

from dpo4000_utils.gui.preferences import GuiPreferences, load_preferences, save_preferences


def test_gui_preferences_round_trip(tmp_path):
    path = tmp_path / "prefs" / "gui_preferences.json"
    prefs = GuiPreferences(
        connection_mode="ethernet",
        visa_resource="TCPIP0::192.168.1.50::INSTR",
        ethernet_host="192.168.1.50",
        read_all_parameters_after_connection=False,
        output_folder="D:/scope-output",
        png_base="transient",
        png_add_timestamp=False,
    )

    written = save_preferences(prefs, path)
    loaded = load_preferences(written)

    assert written == path
    assert loaded == prefs


def test_load_preferences_missing_file_returns_defaults(tmp_path):
    loaded = load_preferences(tmp_path / "missing.json")

    assert loaded == GuiPreferences()


def test_load_preferences_invalid_json_returns_defaults(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")

    loaded = load_preferences(path)

    assert loaded == GuiPreferences()


def test_partial_preferences_keep_defaults(tmp_path):
    path = tmp_path / "partial.json"
    path.write_text(json.dumps({"connection_mode": "ethernet"}), encoding="utf-8")

    loaded = load_preferences(path)

    assert loaded.connection_mode == "ethernet"
    assert loaded.timeout_ms == GuiPreferences().timeout_ms
    assert loaded.read_all_parameters_after_connection is True
    assert loaded.png_prefix == GuiPreferences().png_prefix


def test_preferences_ignore_unknown_keys_and_coerce_bool_strings(tmp_path):
    path = tmp_path / "legacy.json"
    path.write_text(
        json.dumps(
            {
                "read_all_parameters_after_connection": "false",
                "png_add_timestamp": "false",
                "csv_add_timestamp": "yes",
                "unknown_old_key": "ignored",
            }
        ),
        encoding="utf-8",
    )

    loaded = load_preferences(path)

    assert loaded.read_all_parameters_after_connection is False
    assert loaded.png_add_timestamp is False
    assert loaded.csv_add_timestamp is True
    assert not hasattr(loaded, "unknown_old_key")
