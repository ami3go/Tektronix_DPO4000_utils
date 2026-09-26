"""Canonical 11-page desktop layout with A15 Recipe and Logger pages."""

from __future__ import annotations

import sys

RECIPE_PAGE_INDEX = 6
LOGGER_PAGE_INDEX = 7
FILE_PAGE_INDEX = 8
DISPLAY_PAGE_INDEX = 9
LOG_PAGE_INDEX = 10
CONTROL_TAB_TITLES = (
    "Connection",
    "Channels",
    "Measurement",
    "Trigger",
    "Acquisition",
    "Automation",
    "Recipe",
    "Logger",
    "File",
    "Display",
    "Log",
)
CONTROL_PAGE_BUILDERS = (
    "_build_connection_tab",
    "_build_channels_tab",
    "_build_measurement_tab",
    "_build_trigger_tab",
    "_build_acquisition_tab",
    "_build_automation_tab",
    "_build_recipe_tab",
    "_build_logger_tab",
    "_build_file_tab",
    "_build_display_tab",
    "_build_log_tab",
)

# Preserve every pre-A15 page shortcut. Recipe gets a new non-conflicting shortcut.
PAGE_SHORTCUTS = (
    ("Ctrl+1", 0, "Connection"),
    ("Ctrl+2", 1, "Channels"),
    ("Ctrl+3", 2, "Measurement"),
    ("Ctrl+4", 3, "Trigger"),
    ("Ctrl+5", 4, "Acquisition"),
    ("Ctrl+6", 5, "Automation"),
    ("Ctrl+Shift+6", RECIPE_PAGE_INDEX, "Recipe"),
    ("Ctrl+7", LOGGER_PAGE_INDEX, "Logger"),
    ("Ctrl+8", FILE_PAGE_INDEX, "File"),
    ("Ctrl+9", DISPLAY_PAGE_INDEX, "Display"),
    ("Ctrl+0", LOG_PAGE_INDEX, "Log"),
)


def install_logger_page_layout() -> None:
    """Patch layered GUI modules before the final production window is constructed.

    Older Automation layers resolve module globals at call time. Updating the
    captured page lists and File/Display/Log indexes here preserves their routing
    after A15 Recipe is inserted before Logger without introducing another
    navigation stack.
    """
    from . import (
        automation_window,
        collapsible_window,
        display_window,
        titlebar_tabs_window,
    )

    display_window.CONTROL_TAB_TITLES = CONTROL_TAB_TITLES
    display_window.CONTROL_PAGE_BUILDERS = CONTROL_PAGE_BUILDERS
    display_window.DISPLAY_PAGE_SHORTCUTS = PAGE_SHORTCUTS
    display_window.FILE_PAGE_INDEX = FILE_PAGE_INDEX
    display_window.DISPLAY_PAGE_INDEX = DISPLAY_PAGE_INDEX
    display_window.LOG_PAGE_INDEX = LOG_PAGE_INDEX

    automation_window.CONTROL_TAB_TITLES = CONTROL_TAB_TITLES
    automation_window.CONTROL_PAGE_BUILDERS = CONTROL_PAGE_BUILDERS
    automation_window.PAGE_SHORTCUTS = PAGE_SHORTCUTS
    automation_window.FILE_PAGE_INDEX = FILE_PAGE_INDEX
    automation_window.DISPLAY_PAGE_INDEX = DISPLAY_PAGE_INDEX
    automation_window.LOG_PAGE_INDEX = LOG_PAGE_INDEX

    titlebar_tabs_window.CONTROL_TAB_TITLES = CONTROL_TAB_TITLES
    collapsible_window.SETTINGS_PAGE_INDEX = FILE_PAGE_INDEX
    collapsible_window.PREFERENCE_PAGE_INDEXES = (
        collapsible_window.CONNECTION_PAGE_INDEX,
        collapsible_window.TRIGGER_PAGE_INDEX,
        FILE_PAGE_INDEX,
    )

    prefix = "dpo4000_utils.gui_qt.automation"
    for name, module in tuple(sys.modules.items()):
        if (
            name.startswith(prefix)
            and module is not None
            and hasattr(module, "FILE_PAGE_INDEX")
        ):
            setattr(module, "FILE_PAGE_INDEX", FILE_PAGE_INDEX)


__all__ = [
    "CONTROL_PAGE_BUILDERS",
    "CONTROL_TAB_TITLES",
    "DISPLAY_PAGE_INDEX",
    "FILE_PAGE_INDEX",
    "LOGGER_PAGE_INDEX",
    "LOG_PAGE_INDEX",
    "PAGE_SHORTCUTS",
    "RECIPE_PAGE_INDEX",
    "install_logger_page_layout",
]
