from __future__ import annotations

from threading import Event

import pytest

from dpo4000_utils.logger.models import LoggerConfig, LoggerMode
from dpo4000_utils.logger.producer import LoggerCaptureCancelled, capture_logger_record


class _CancelledScope:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def single_acquisition(self) -> None:
        self.calls.append("single")

    def stop_acquisition(self) -> None:
        self.calls.append("stop")


def test_mixed_config_accepts_measurement_only_source_group() -> None:
    config = LoggerConfig(
        mode=LoggerMode.MIXED,
        waveform_sources=(),
        measurement_slots=(1, 2),
    )
    assert config.waveform_sources == ()
    assert config.measurement_slots == (1, 2)


def test_mixed_config_rejects_empty_job() -> None:
    with pytest.raises(ValueError, match="at least one source"):
        LoggerConfig(
            mode=LoggerMode.MIXED,
            waveform_sources=(),
            measurement_slots=(),
            bus_slots=(),
        )


def test_mixed_capture_cancels_single_before_reading_components() -> None:
    scope = _CancelledScope()
    cancel = Event()
    cancel.set()
    config = LoggerConfig(
        mode=LoggerMode.MIXED,
        waveform_sources=(),
        measurement_slots=(1,),
    )

    with pytest.raises(LoggerCaptureCancelled):
        capture_logger_record(scope, config, 1, cancel_event=cancel)

    assert scope.calls == ["single", "stop"]
