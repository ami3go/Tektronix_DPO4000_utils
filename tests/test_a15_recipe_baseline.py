from __future__ import annotations

import pytest

from dpo4000_utils.recipe_baseline import capture_recipe_timing


class FakeScope:
    def __init__(self) -> None:
        self.holdoff_reads = 0
        self.trigger_reads = 0

    def get_trigger_holdoff(self) -> float:
        self.holdoff_reads += 1
        return 1e-6

    def get_trigger_configuration(self) -> dict[str, object]:
        self.trigger_reads += 1
        return {"trigger_type": "EDGE", "holdoff": 1e-6}


def test_a15_recipe_timing_capture_has_required_r0_t_metrics() -> None:
    scope = FakeScope()
    result = capture_recipe_timing(scope, reps=2, dispatch_steps=50)
    assert result["recipe_completion"]["sample_count"] == 2
    assert result["step_dispatch_overhead"]["sample_count"] == 2
    assert result["dispatch_steps_per_sample"] == 50
    assert scope.holdoff_reads == 2
    assert scope.trigger_reads == 2


@pytest.mark.parametrize(
    ("field", "kwargs"),
    [
        ("reps", {"reps": 0}),
        ("reps", {"reps": True}),
        ("dispatch_steps", {"dispatch_steps": 0}),
        ("dispatch_steps", {"dispatch_steps": True}),
    ],
)
def test_a15_recipe_timing_rejects_invalid_work_sizes(field, kwargs) -> None:
    with pytest.raises(ValueError, match=field):
        capture_recipe_timing(FakeScope(), **kwargs)
