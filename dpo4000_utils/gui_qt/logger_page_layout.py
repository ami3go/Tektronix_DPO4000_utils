"""Canonical 10-page desktop layout after inserting the Logger tab."""

from __future__ import annotations

import sys

LOGGER_PAGE_INDEX = 6
FILE_PAGE_INDEX = 7
DISPLAY_PAGE_INDEX = 8
LOG_PAGE_INDEX = 9
CONTROL_TAB_TITLES = (
    "Connection",
    "Channels",
    "Measurement",
    "Trigger",
    "Acquisition",
    "Automation",
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
    "_build_logger_tab",
    "_build_file_tab",
    "_build_display_tab",
    "_build_log_tab",
)
PAGE_SHORTCUTS = tuple(
    [(f"Ctrl+{index + 1}", index, title) for index, title in enumerate(CONTROL_TAB_TITLES[:9])]
    + [("Ctrl+0", 9, "Log")]
)


def install_logger_page_layout() -> None:
    """Patch already-imported layered GUI modules before the final window is constructed.

    Older Automation layers resolve their module globals at call time. Updating all
    captured FILE_PAGE_INDEX globals here preserves their File-page routing after
    Logger is inserted before File, without introducing a second navigation stack.
    """
    from . import automation_window, collapsible_window, display_window, titlebar_tabs_window

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
        if name.startswith(prefix) and module is not None and hasattr(module, "FILE_PAGE_INDEX"):
            setattr(module, "FILE_PAGE_INDEX", FILE_PAGE_INDEX)


__all__ = [
    "CONTROL_PAGE_BUILDERS",
    "CONTROL_TAB_TITLES",
    "DISPLAY_PAGE_INDEX",
    "FILE_PAGE_INDEX",
    "LOGGER_PAGE_INDEX",
    "LOG_PAGE_INDEX",
    "PAGE_SHORTCUTS",
    "install_logger_page_layout",
]
