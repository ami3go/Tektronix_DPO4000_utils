import json

import pytest

from dpo4000_utils.errors import DPOSettingsError
from dpo4000_utils.settings import (
    SETTINGS_SCHEMA_VERSION,
    SETUP_FORMAT,
    apply_scope_settings_file,
    apply_setup_string,
    build_scope_settings_payload,
    load_scope_settings_file,
    resolve_settings_path,
    validate_scope_settings_payload,
)


class FakeScope:
    def __init__(self, responses=None):
        self.responses = dict(responses or {})
        self.commands = []
        self.timeout = 1234

    def write(self, command):
        self.commands.append(("write", command))

    def query(self, command):
        self.commands.append(("query", command))
        response = self.responses.get(command)
        if isinstance(response, Exception):
            raise response
        if response is None:
            return "0"
        return response


def test_resolve_settings_path_adds_folder_and_suffix_without_creating_directory(tmp_path):
    path = resolve_settings_path("setup_file", settings_folder=tmp_path / "settings")
    assert path == tmp_path / "settings" / "setup_file.json"
    assert not path.parent.exists()


def test_load_scope_settings_file_validates_setup(tmp_path):
    file_path = tmp_path / "bad.json"
    file_path.write_text(json.dumps({"instrument": "scope"}), encoding="utf-8")

    with pytest.raises(DPOSettingsError, match="missing or empty 'setup'"):
        load_scope_settings_file(file_path)


def test_invalid_json_uses_stable_settings_exception(tmp_path):
    file_path = tmp_path / "bad.json"
    file_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(DPOSettingsError, match="valid JSON"):
        load_scope_settings_file(file_path)


def test_build_scope_settings_payload_is_versioned_and_does_not_clear_status():
    scope = FakeScope({"*IDN?": "TEKTRONIX,DPO4054,SN,1.0\n", "*LRN?": ":SETUP DATA\n"})

    payload = build_scope_settings_payload(scope)

    assert payload["schema_version"] == SETTINGS_SCHEMA_VERSION
    assert payload["instrument"] == "TEKTRONIX,DPO4054,SN,1.0"
    assert payload["setup"] == ":SETUP DATA"
    assert payload["setup_format"] == SETUP_FORMAT
    assert ("write", "*CLS") not in scope.commands


def test_build_scope_settings_payload_falls_back_to_set_query():
    scope = FakeScope(
        {
            "*IDN?": "TEKTRONIX,DPO4054,SN,1.0",
            "*LRN?": RuntimeError("unsupported"),
            "SET?": ":SET FALLBACK\n",
        }
    )

    payload = build_scope_settings_payload(scope)

    assert payload["setup"] == ":SET FALLBACK"


def test_apply_setup_string_restores_timeout_after_opc():
    scope = FakeScope({"*OPC?": "1", "*ESR?": "0"})

    apply_setup_string(
        scope, ":SETUP DATA", wait_complete=True, restore_delay_s=0.0, opc_timeout_ms=9876
    )

    assert scope.timeout == 1234
    assert scope.commands[:2] == [("write", "*CLS"), ("write", ":SETUP DATA")]
    assert ("query", "*OPC?") in scope.commands
    assert ("query", "*ESR?") in scope.commands


def test_apply_setup_string_reports_scope_errors_with_stable_exception():
    scope = FakeScope({"*ESR?": "1", "ALLEV?": "200,Execution error"})

    with pytest.raises(DPOSettingsError, match="Scope reported error"):
        apply_setup_string(scope, ":SETUP DATA", restore_delay_s=0.0)

    assert ("query", "ALLEV?") in scope.commands


def test_apply_scope_settings_file_returns_legacy_payload(tmp_path):
    file_path = tmp_path / "setup.json"
    file_path.write_text(
        json.dumps({"instrument": "TEK", "setup": ":SETUP DATA"}),
        encoding="utf-8",
    )
    scope = FakeScope({"*IDN?": "TEKTRONIX,DPO4054,SN,1.0", "*ESR?": "0"})

    payload = apply_scope_settings_file(scope, file_path, restore_delay_s=0.0)

    assert payload["instrument"] == "TEK"
    assert ("write", ":SETUP DATA") in scope.commands


def test_payload_rejects_wrong_format_and_incompatible_manufacturer():
    with pytest.raises(DPOSettingsError, match="Unsupported setup_format"):
        validate_scope_settings_payload(
            {
                "schema_version": SETTINGS_SCHEMA_VERSION,
                "setup_format": "foreign_format",
                "setup": ":SETUP DATA",
            }
        )

    with pytest.raises(DPOSettingsError, match="non-Tektronix"):
        validate_scope_settings_payload(
            {
                "schema_version": SETTINGS_SCHEMA_VERSION,
                "setup_format": SETUP_FORMAT,
                "instrument": "ACME,MODEL1,SN,1.0",
                "setup": ":SETUP DATA",
            },
            connected_identity="TEKTRONIX,DPO4054,SN,1.0",
        )


def test_payload_allows_compatible_dpo4000_model_with_warning():
    payload = {
        "schema_version": SETTINGS_SCHEMA_VERSION,
        "setup_format": SETUP_FORMAT,
        "instrument": "TEKTRONIX,DPO4104,SN,1.0",
        "setup": ":SETUP DATA",
    }
    with pytest.warns(RuntimeWarning, match="compatible"):
        assert (
            validate_scope_settings_payload(
                payload,
                connected_identity="TEKTRONIX,DPO4054,SN,1.0",
            )
            is payload
        )
