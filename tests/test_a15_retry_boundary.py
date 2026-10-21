from __future__ import annotations

import pytest

from dpo4000_utils.recipe import RecipeValidationError, RetryPolicy


@pytest.mark.parametrize("delay", [float("nan"), float("inf"), -0.001])
def test_retry_delay_must_be_finite_non_negative(delay: float) -> None:
    with pytest.raises(RecipeValidationError):
        RetryPolicy(delay_s=delay)


@pytest.mark.parametrize("backoff", [float("nan"), float("inf"), 0.999])
def test_retry_backoff_must_be_finite_at_least_one(backoff: float) -> None:
    with pytest.raises(RecipeValidationError):
        RetryPolicy(backoff=backoff)
