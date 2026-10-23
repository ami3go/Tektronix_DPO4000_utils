"""A22 instrument ownership, bounded memory and forbidden GUI operations."""
from pathlib import Path

from dpo4000_utils.live_stream import LiveStreamEngine, StreamConfig

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "dpo4000_utils/gui_qt/composition/pages/live_waveform.py"
BOUNDARY = ROOT / "dpo4000_utils/gui_qt/composition/legacy_surface.py"


def test_qt_does_not_issue_raw_scpi_or_own_visa():
    text = PANEL.read_text(encoding="utf-8")
    for forbidden in ("scope.scope", ".write(", ".query(", "ResourceManager(", "eval(", "exec("):
        assert forbidden not in text
    assert "capture_frame(scope, config" in text
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
