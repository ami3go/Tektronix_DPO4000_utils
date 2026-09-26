from __future__ import annotations

from dpo4000_utils.recipe import Recipe, RecipeRunState, RecipeSequencer, RecipeStep


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class Target:
    def ping(self, value: int) -> int:
        return value


def test_large_recipe_preserves_order_without_recursion() -> None:
    clock = Clock()
    recipe = Recipe(
        "large",
        tuple(RecipeStep.call("ping", index) for index in range(2000)),
    )
    result = RecipeSequencer(
        Target(),
        monotonic=clock.monotonic,
        sleep=clock.sleep,
    ).run(recipe)
    assert result.state is RecipeRunState.COMPLETED
    assert len(result.steps) == 2000
    assert result.steps[0].value == 0
    assert result.steps[-1].value == 1999
