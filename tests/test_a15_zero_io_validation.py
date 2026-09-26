from __future__ import annotations

import pytest

from dpo4000_utils.recipe import RecipeValidationError, recipe_from_mapping


class BombTarget:
    def __getattr__(self, name):
        raise AssertionError(f"unexpected target access: {name}")


def test_invalid_document_needs_no_target_access() -> None:
    target = BombTarget()
    del target
    with pytest.raises(RecipeValidationError):
        recipe_from_mapping({"name": "x", "steps": [{"kind": "delay", "seconds": -0.1}]})
