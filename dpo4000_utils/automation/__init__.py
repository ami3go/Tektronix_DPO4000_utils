"""Reusable automation models for DPO4000 Desk."""

from .bundle import (
    CancelSignal,
    TriggerBundleResult,
    acquire_trigger_bundle,
    collision_safe_bundle_paths,
)
from .periodic import (
    AutomationEventToken,
    AutomationState,
    AutomationStatistics,
    PeriodicImageConfig,
    PeriodicImageController,
    append_sequence,
    collision_safe_path,
)
from .triggered import (
    TriggerImageConfig,
    TriggerImageController,
    TriggerWaitResult,
    trigger_acquisition_complete,
)
from .waveform_logging import TimedWaveformResult, save_full_record_csv

__all__ = [
    "AutomationEventToken",
    "AutomationState",
    "AutomationStatistics",
    "CancelSignal",
    "PeriodicImageConfig",
    "PeriodicImageController",
    "TimedWaveformResult",
    "TriggerBundleResult",
    "TriggerImageConfig",
    "TriggerImageController",
    "TriggerWaitResult",
    "acquire_trigger_bundle",
    "append_sequence",
    "collision_safe_bundle_paths",
    "collision_safe_path",
    "save_full_record_csv",
    "trigger_acquisition_complete",
]
