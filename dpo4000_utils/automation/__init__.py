"""Reusable automation models for DPO4000 Desk."""

from .artifacts import (
    ArtifactAction,
    ArtifactCaptureResult,
    capture_artifacts,
    normalize_artifact_action,
)
from .bundle import (
    CancelSignal,
    TriggerBundleResult,
    acquire_trigger_bundle,
    collision_safe_bundle_paths,
)
from .burst import BurstConfig, BurstEventResult, run_burst_event
from .conditional import (
    CONDITION_OPERATORS,
    ConditionEvaluation,
    ConditionalCaptureConfig,
    ConditionalEvaluator,
    ConditionalPollResult,
    parse_measurement_value,
    run_conditional_poll,
)
from .measurement_logging import (
    MeasurementLogResult,
    append_measurement_row,
    normalize_measurement_slots,
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
    "ArtifactAction",
    "ArtifactCaptureResult",
    "AutomationEventToken",
    "AutomationState",
    "AutomationStatistics",
    "BurstConfig",
    "BurstEventResult",
    "CONDITION_OPERATORS",
    "CancelSignal",
    "ConditionEvaluation",
    "ConditionalCaptureConfig",
    "ConditionalEvaluator",
    "ConditionalPollResult",
    "MeasurementLogResult",
    "PeriodicImageConfig",
    "PeriodicImageController",
    "TimedWaveformResult",
    "TriggerBundleResult",
    "TriggerImageConfig",
    "TriggerImageController",
    "TriggerWaitResult",
    "acquire_trigger_bundle",
    "append_measurement_row",
    "append_sequence",
    "capture_artifacts",
    "collision_safe_bundle_paths",
    "collision_safe_path",
    "normalize_artifact_action",
    "normalize_measurement_slots",
    "parse_measurement_value",
    "run_burst_event",
    "run_conditional_poll",
    "save_full_record_csv",
    "trigger_acquisition_complete",
]
