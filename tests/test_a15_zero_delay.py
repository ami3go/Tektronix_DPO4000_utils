from dpo4000_utils.recipe import Recipe, RecipeRunState, RecipeSequencer, RecipeStep


def test_zero_delay_is_valid_and_completes() -> None:
    result = RecipeSequencer(object()).run(Recipe("zero", (RecipeStep.delay(0),)))
    assert result.state is RecipeRunState.COMPLETED
