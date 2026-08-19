import json

import pytest

from dpo4000_utils.settings import (
    apply_scope_settings_file,
    apply_setup_string,
    build_scope_settings_payload,
    load_scope_settings_file,
    resolve_settings_path,
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


def test_resolve_settings_path_adds_folder_and_suffix(tmp_path):
    path = resolve_settings_path("setup_file", settings_folder=tmp_path)
    assert path == tmp_path / "setup_file.json"
    assert path.parent.exists()


def test_load_scope_settings_file_validates_setup(tmp_path):
    file_path = tmp_path / "bad.json"
    file_path.write_text(json.dumps({"instrument": "scope"}), encoding="utf-8")

    with pytest.raises(ValueError, match="missing or empty 'setup'"):
        load_scope_settings_file(file_path)


def test_build_scope_settings_payload_uses_lrn_first():
    scope = FakeScope({"*IDN?": "TEK,DPO4054\n", "*LRN?": ":SETUP DATA\n"})

    payload = build_scope_settings_payload(scope)

    assert payload["instrument"] == "TEK,DPO4054"
    assert payload["setup"] == ":SETUP DATA"
    assert payload["setup_format"] == "tektronix_scpi_lrn"
    assert ("write", "*CLS") in scope.commands


def test_build_scope_settings_payload_falls_back_to_set_query():
    scope = FakeScope({"*LRN?": RuntimeError("unsupported"), "SET?": ":SET FALLBACK\n"})

    payload = build_scope_settings_payload(scope)

    assert payload["setup"] == ":SET FALLBACK"


def test_apply_setup_string_restores_timeout_after_opc():
    scope = FakeScope({"*OPC?": "1", "*ESR?": "0"})

    apply_setup_string(scope, ":SETUP DATA", wait_complete=True, restore_delay_s=0.0, opc_timeout_ms=9876)

    assert scope.timeout == 1234
    assert scope.commands[:2] == [("write", "*CLS"), ("write", ":SETUP DATA")]
    assert ("query", "*OPC?") in scope.commands
    assert ("query", "*ESR?") in scope.commands


def test_apply_setup_string_reports_scope_errors():
    scope = FakeScope({"*ESR?": "1", "ALLEV?": "200,Execution error"})

    with pytest.raises(RuntimeError, match="Scope reported error"):
        apply_setup_string(scope, ":SETUP DATA", restore_delay_s=0.0)

    assert ("query", "ALLEV?") in scope.commands


def test_apply_scope_settings_file_returns_payload(tmp_path):
    file_path = tmp_path / "setup.json"
    file_path.write_text(
        json.dumps({"instrument": "TEK", "setup": ":SETUP DATA"}),
        encoding="utf-8",
    )
    scope = FakeScope({"*ESR?": "0"})

    payload = apply_scope_settings_file(scope, file_path, restore_delay_s=0.0)

    assert payload["instrument"] == "TEK"
    assert ("write", ":SETUP DATA") in scope.commands
