from __future__ import annotations

import pytest

from dpo4000_utils.recipe import RecipeStep, RecipeValidationError


@pytest.mark.parametrize("seconds", [True, None, "1", -1, float("nan"), float("inf")])
def test_delay_rejects_invalid_values(seconds) -> None:
    with pytest.raises(RecipeValidationError):
        RecipeStep.delay(seconds)
