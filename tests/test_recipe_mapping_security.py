from __future__ import annotations

import pytest

from dpo4000_utils.recipe import RecipeValidationError, recipe_from_mapping


@pytest.mark.parametrize(
    "method",
    [
        "write;*RST",
        "query\n*IDN?",
        "query\r*IDN?",
        "_session",
        "scope.query",
        "",
    ],
)
def test_recipe_method_name_cannot_encode_raw_scpi_or_private_access(method: str) -> None:
    with pytest.raises(RecipeValidationError):
        recipe_from_mapping(
            {
                "name": "unsafe",
                "steps": [{"kind": "call", "method": method}],
            }
        )


def test_recipe_rejects_unknown_top_level_fields() -> None:
    with pytest.raises(RecipeValidationError):
        recipe_from_mapping(
            {
                "name": "unsafe",
                "steps": [{"kind": "delay", "seconds": 0}],
                "future_field": "must not be silently ignored",
            }
        )
