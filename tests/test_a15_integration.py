from __future__ import annotations

import pytest

from dpo4000_utils.control import ChannelConfig
from dpo4000_utils.gui_qt.logger_page_layout import (
    CONTROL_PAGE_BUILDERS,
    CONTROL_TAB_TITLES,
    DISPLAY_PAGE_INDEX,
    FILE_PAGE_INDEX,
    LOGGER_PAGE_INDEX,
    LOG_PAGE_INDEX,
    PAGE_SHORTCUTS,
    RECIPE_PAGE_INDEX,
)
from dpo4000_utils.recipe import (
    Recipe,
    RecipeRunState,
    RecipeSequencer,
    RecipeStep,
    RecipeValidationError,
    recipe_from_mapping,
)


def test_recipe_navigation_is_inserted_without_reassigning_existing_shortcuts() -> None:
    assert CONTROL_TAB_TITLES[RECIPE_PAGE_INDEX] == "Recipe"
    assert CONTROL_PAGE_BUILDERS[RECIPE_PAGE_INDEX] == "_build_recipe_tab"
    assert LOGGER_PAGE_INDEX == 7
    assert FILE_PAGE_INDEX == 8
    assert DISPLAY_PAGE_INDEX == 9
    assert LOG_PAGE_INDEX == 10
    shortcut_map = {title: key for key, _index, title in PAGE_SHORTCUTS}
    assert shortcut_map["Automation"] == "Ctrl+6"
    assert shortcut_map["Recipe"] == "Ctrl+Shift+6"
    assert shortcut_map["Logger"] == "Ctrl+7"
    assert shortcut_map["File"] == "Ctrl+8"
    assert shortcut_map["Display"] == "Ctrl+9"
    assert shortcut_map["Log"] == "Ctrl+0"


def test_later_missing_method_is_rejected_before_first_recipe_io() -> None:
    calls: list[str] = []

    class Target:
        def first(self) -> None:
            calls.append("first")

    result = RecipeSequencer(Target()).run(
        Recipe(
            "preflight",
            (
                RecipeStep.call("first"),
                RecipeStep.call("missing"),
            ),
        )
    )
    assert result.state is RecipeRunState.FAILED
    assert calls == []
    assert "RecipeValidationError" in (result.error or "")


def test_json_config_mapping_is_coerced_to_public_driver_config_type() -> None:
    seen: list[ChannelConfig] = []

    class Target:
        def configure_channel(self, config: ChannelConfig) -> None:
            seen.append(config)

    recipe = recipe_from_mapping(
        {
            "version": 1,
            "name": "channel config",
            "steps": [
                {
                    "kind": "call",
                    "method": "configure_channel",
                    "args": [{"channel": 2, "display": True, "scale": 0.5}],
                }
            ],
        }
    )
    result = RecipeSequencer(Target()).run(recipe)
    assert result.state is RecipeRunState.COMPLETED
    assert seen == [ChannelConfig(channel=2, display=True, scale=0.5)]


def test_mapping_can_forward_method_kwarg_named_name() -> None:
    seen: list[str] = []

    class Target:
        def label(self, *, name: str) -> None:
            seen.append(name)

    recipe = recipe_from_mapping(
        {
            "name": "reserved kwarg",
            "steps": [
                {
                    "kind": "call",
                    "method": "label",
                    "kwargs": {"name": "CH1"},
                }
            ],
        }
    )
    assert RecipeSequencer(Target()).run(recipe).state is RecipeRunState.COMPLETED
    assert seen == ["CH1"]


@pytest.mark.parametrize(
    "method",
    [
        "connect",
        "disconnect",
        "ensure_connected",
        "configure_session",
        "temporary_timeout",
        "probe_scpi_query",
    ],
)
def test_transport_and_raw_probe_methods_are_not_recipe_operations(method: str) -> None:
    with pytest.raises(RecipeValidationError):
        recipe_from_mapping(
            {
                "name": "unsafe",
                "steps": [{"kind": "call", "method": method}],
            }
        )


def test_pause_time_does_not_consume_delay_budget() -> None:
    class Clock:
        def __init__(self) -> None:
            self.now = 0.0
            self.sleeps: list[float] = []

        def monotonic(self) -> float:
            return self.now

        def sleep(self, seconds: float) -> None:
            self.sleeps.append(seconds)
            self.now += seconds
            if len(self.sleeps) == 1:
                sequencer.pause()
            elif sequencer.state is RecipeRunState.PAUSED and self.now >= 0.25:
                sequencer.resume()

    clock = Clock()
    sequencer = RecipeSequencer(
        object(),
        monotonic=clock.monotonic,
        sleep=clock.sleep,
        cancel_poll_s=0.05,
    )
    result = sequencer.run(Recipe("pause delay", (RecipeStep.delay(0.1),)))
    assert result.state is RecipeRunState.COMPLETED
    # 0.1 s active Delay + 0.2 s intentionally paused.
    assert result.duration_s == pytest.approx(0.3)
