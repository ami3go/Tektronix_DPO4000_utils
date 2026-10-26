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
    restore_setup_verified,
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

    apply_setup_string(scope, ":SETUP DATA", wait_complete=True, restore_delay_s=0.0, opc_timeout_ms=9876)

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
        assert validate_scope_settings_payload(
            payload,
            connected_identity="TEKTRONIX,DPO4054,SN,1.0",
        ) is payload


class Clock:
    """Deterministic monotonic clock + sleep for settling tests."""

    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class SettlingScope:
    """Fake scope that applies a setup asynchronously, like the DPO4054.

    After a write, dependent settings (cursor positions) read back wrong until
    ``settle_s`` has elapsed on the shared clock. ``applies_needed`` models a setup that is
    only accepted on a later application.
    """

    def __init__(self, clock, state, settle_s=3.0, applies_needed=1):
        self.clock = clock
        self.state = state
        self.settle_s = settle_s
        self.applies_needed = applies_needed
        self.applied = 0
        self.target = None
        self.applied_at = None
        self.timeout = 1000

    def write(self, command):
        if command == "*CLS":
            return
        self.applied += 1
        self.target = command
        self.applied_at = self.clock.now
        if self.applied < self.applies_needed:
            self.target = None  # not accepted this time

    def query(self, command):
        assert command in {"*LRN?", "SET?"}
        if self.target is not None:
            settled = self.clock.now - self.applied_at >= self.settle_s
            self.state = self.target if settled else self.target + ";UNSETTLED"
        return self.state


def _restore(scope, clock, setup, **kwargs):
    return restore_setup_verified(
        scope, setup, restore_delay_s=0, sleep=clock.sleep, monotonic=clock.monotonic, **kwargs
    )


def test_restore_setup_verified_is_a_no_op_when_already_exact():
    clock = Clock()
    scope = SettlingScope(clock, ":A 1;:B 2")
    assert _restore(scope, clock, ":A 1;:B 2") == (True, 0, ":A 1;:B 2")
    assert scope.applied == 0


def test_restore_setup_verified_waits_for_the_scope_to_settle_instead_of_reapplying():
    clock = Clock()
    scope = SettlingScope(clock, ":OTHER", settle_s=3.0)
    exact, passes, final = _restore(scope, clock, ":A 1;:B 2")
    assert (exact, passes, final) == (True, 1, ":A 1;:B 2")
    assert scope.applied == 1  # a re-apply would restart the settling window
    assert 3.0 <= clock.now < 4.0


def test_restore_setup_verified_reapplies_when_the_first_apply_was_not_accepted():
    clock = Clock()
    scope = SettlingScope(clock, ":OTHER", settle_s=1.0, applies_needed=2)
    exact, passes, _final = _restore(scope, clock, ":A 1", settle_timeout_s=3.0)
    assert (exact, passes) == (True, 2)


def test_restore_setup_verified_gives_up_after_max_passes_and_reports_the_mismatch():
    clock = Clock()
    scope = SettlingScope(clock, ":OTHER", settle_s=999.0)
    exact, passes, final = _restore(scope, clock, ":A 1", max_passes=2, settle_timeout_s=2.0)
    assert exact is False and passes == 2 and scope.applied == 2
    assert final.endswith(";UNSETTLED")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_passes": 0}, {"max_passes": True}, {"max_passes": 1.5},
        {"settle_timeout_s": 0}, {"settle_timeout_s": float("nan")},
        {"poll_interval_s": -1}, {"poll_interval_s": True},
    ],
)
def test_restore_setup_verified_validates_arguments(kwargs):
    clock = Clock()
    with pytest.raises(ValueError):
        _restore(SettlingScope(clock, ":A"), clock, ":A", **kwargs)
