from __future__ import annotations

import sys
from array import array

from dpo4000_utils.logger.models import WaveformSnapshot


def test_snapshot_restores_opposite_endian_samples() -> None:
    values = array("h", [1, -2, 300])
    raw = array("h", values)
    raw.byteswap()
    snapshot = WaveformSnapshot(
        source="CH1",
        label="CH1",
        start_index=1,
        stop_index=3,
        acquired_utc="t",
        typecode="h",
        sample_bytes=raw.tobytes(),
        sample_count=3,
        byte_order="big" if sys.byteorder == "little" else "little",
        preamble={"x_zero": 0.0, "x_increment": 1.0, "point_offset": 0.0, "y_offset": 0.0, "y_multiplier": 1.0, "y_zero": 0.0},
    )
    assert snapshot.samples().tolist() == [1, -2, 300]
