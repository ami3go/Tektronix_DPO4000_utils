from __future__ import annotations

import pytest

from dpo4000_utils.recipe import RecipeValidationError, RetryPolicy


@pytest.mark.parametrize("value", [True, 0, -1, 1.5, "2", None])
def test_retry_attempt_count_rejects_non_positive_or_non_integer(value) -> None:
    if value == 0 or value == -1 or value is True or not isinstance(value, int):
        with pytest.raises(RecipeValidationError):
            RetryPolicy(attempts=value)
