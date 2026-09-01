"""Reusable automation models for DPO4000 Desk."""

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
    "PeriodicImageConfig",
    "PeriodicImageController",
    "TriggerImageConfig",
    "TriggerImageController",
    "TriggerWaitResult",
    "append_sequence",
    "collision_safe_path",
    "trigger_acquisition_complete",
]
