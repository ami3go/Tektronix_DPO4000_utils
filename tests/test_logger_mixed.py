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


class _MeasurementMixedScope:
    def __init__(self) -> None:
        self.active = [False, True, False]
        self.trigger = ["SAVE", "READY", "SAVE"]
        self.calls: list[str] = []

    @staticmethod
    def _next(values):
        return values.pop(0) if len(values) > 1 else values[0]

    def get_acquisition_state(self) -> bool:
        self.calls.append("acq")
        return bool(self._next(self.active))

    def get_trigger_state(self) -> str:
        self.calls.append("trigger")
        return str(self._next(self.trigger))

    def single_acquisition(self) -> None:
        self.calls.append("single")

    def stop_acquisition(self) -> None:
        self.calls.append("stop")

    def read_measurement_value(self, slot: int) -> str:
        self.calls.append(f"measure:{slot}")
        return "1.25"


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


def test_mixed_capture_cancelled_before_arm_touches_no_scope_state() -> None:
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

    assert scope.calls == []


def test_mixed_capture_requires_fresh_single_before_components() -> None:
    scope = _MeasurementMixedScope()
    config = LoggerConfig(
        mode=LoggerMode.MIXED,
        waveform_sources=(),
        measurement_slots=(1,),
    )

    record = capture_logger_record(scope, config, 1)

    assert record.measurements[1] == 1.25
    assert record.metadata["acquisition_policy"] == "fresh-single-complete-before-read"
    assert scope.calls == [
        "acq",
        "trigger",
        "single",
        "acq",
        "trigger",
        "acq",
        "trigger",
        "measure:1",
    ]
