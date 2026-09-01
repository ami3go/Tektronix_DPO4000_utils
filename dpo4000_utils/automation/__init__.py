"""Reusable automation models for DPO4000 Desk."""

from .bundle import CancelSignal, TriggerBundleResult, acquire_trigger_bundle
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

__all__ = [
    "AutomationEventToken",
    "AutomationState",
    "AutomationStatistics",
    "CancelSignal",
    "PeriodicImageConfig",
    "PeriodicImageController",
    "TriggerBundleResult",
    "TriggerImageConfig",
    "TriggerImageController",
    "TriggerWaitResult",
    "acquire_trigger_bundle",
    "append_sequence",
    "collision_safe_path",
    "trigger_acquisition_complete",
]
