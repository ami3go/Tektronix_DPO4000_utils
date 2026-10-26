"""A22 instrument ownership, bounded memory and forbidden GUI operations."""
from pathlib import Path
from runpy import run_path

import pytest

from dpo4000_utils.live_stream import LiveStreamEngine, StreamConfig

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "dpo4000_utils/gui_qt/composition/pages/live_waveform.py"
BOUNDARY = ROOT / "dpo4000_utils/gui_qt/composition/legacy_surface.py"


def test_qt_does_not_issue_raw_scpi_or_own_visa():
    text = PANEL.read_text(encoding="utf-8")
    for forbidden in ("scope.scope", ".write(", ".query(", "ResourceManager(", "eval(", "exec("):
        assert forbidden not in text
    assert "capture_group(scope, config" in text
    assert "retain_session=True" in text


def test_instrument_ownership_gate_at_shared_dispatch_boundary():
    text = BOUNDARY.read_text(encoding="utf-8")
    assert "_composition_live_lease" in text
    assert "A22 owns the instrument" in text
    assert "on_error(error)" in text
    assert "panel.shutdown()" in text


def test_buffer_never_contains_more_than_one_unrendered_frame():
    engine = LiveStreamEngine()
    assert engine.pending_frames == 0
    for capacity in (1, 2, 8):
        engine.start(StreamConfig(buffer_frames=capacity))
        assert engine.pending_frames <= 1
        engine.stop()
        assert engine.pending_frames == 0


def test_hil_data_snapshot_and_restore_with_synthetic_session():
    hil = run_path(str(ROOT / "tests/hardware/test_a22_live_stream_hardware.py"))
    initial = {
        "SOURCE": "CH2", "START": "11", "STOP": "1000",
        "WIDTH": "1", "ENCDG": "RIBINARY",
    }

    class Session:
        def __init__(self):
            self.values = dict(initial)
            self.writes = []

        def query(self, command):
            return self.values[command.removeprefix("DATA:").removesuffix("?")]

        def write(self, command):
            key, value = command.split(" ", 1)
            self.writes.append(command)
            self.values[key.removeprefix("DATA:")] = value

    session = Session()

    class Scope:
        def ensure_connected(self):
            return session

    scope = Scope()
    assert hil["_data_setup"](scope) == initial
    session.values.update({"SOURCE": "CH1", "START": "1", "WIDTH": "2"})
    assert hil["_restore_data_setup"](scope, initial)
    assert hil["_data_setup"](scope) == initial
    assert len(session.writes) == 6


def test_hil_setup_rejects_untrusted_instrument_response_before_restore():
    hil = run_path(str(ROOT / "tests/hardware/test_a22_live_stream_hardware.py"))

    class Scope:
        def ensure_connected(self):
            return self

        def query(self, command):
            if command == "DATA:SOURCE?":
                return "CH1;*RST"
            return "1"

    with pytest.raises(AssertionError, match="Unsafe or missing"):
        hil["_data_setup"](Scope())


def test_hil_workflow_must_be_reversible_write_not_read_only():
    workflow = (ROOT / ".github/workflows/a22-hil-qualification.yml").read_text(
        encoding="utf-8"
    )
    assert "DPO4000_A22_REVERSIBLE_WRITES" in workflow
    assert "DPO4000_A22_EXCLUSIVE" in workflow
    assert "DPO4000_A22_RESTORE_APPROVED" in workflow
    assert "read-only-hil:" not in workflow
