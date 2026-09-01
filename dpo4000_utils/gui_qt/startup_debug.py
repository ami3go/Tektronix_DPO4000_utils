"""Startup diagnostics for the PySide6 GUI.

This module is intentionally opt-in.  It records top-level Qt widget events and
snapshots during application startup so transient native-looking windows can be
identified without changing normal launch behaviour.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QApplication, QWidget

DEBUG_FLAG = "--startup-debug"
DEBUG_LOG_PREFIX = "--startup-debug-log="
ENV_ENABLE = "DPO4000_QT_STARTUP_DEBUG"
ENV_LOG = "DPO4000_QT_STARTUP_LOG"
DEFAULT_LOG_NAME = "dpo4000_qt_startup_debug.log"
_TRUE_VALUES = {"1", "true", "yes", "on", "debug"}

_EVENT_NAMES = {
    QEvent.Type.Create: "Create",
    QEvent.Type.Destroy: "Destroy",
    QEvent.Type.Show: "Show",
    QEvent.Type.Hide: "Hide",
    QEvent.Type.ShowToParent: "ShowToParent",
    QEvent.Type.HideToParent: "HideToParent",
    QEvent.Type.ParentChange: "ParentChange",
    QEvent.Type.Polish: "Polish",
    QEvent.Type.WinIdChange: "WinIdChange",
    QEvent.Type.WindowActivate: "WindowActivate",
    QEvent.Type.WindowDeactivate: "WindowDeactivate",
}
_MONITORED_EVENTS = frozenset(_EVENT_NAMES)


@dataclass(frozen=True)
class StartupDebugConfig:
    """Parsed startup-debug configuration."""

    enabled: bool
    log_path: Path
    argv: list[str]


def parse_startup_debug_args(argv: Sequence[str] | None = None) -> StartupDebugConfig:
    """Parse and strip startup-debug arguments before QApplication sees them."""
    raw_argv = list(sys.argv if argv is None else argv)
    enabled = os.environ.get(ENV_ENABLE, "").strip().lower() in _TRUE_VALUES
    log_path = Path(os.environ.get(ENV_LOG, "").strip() or DEFAULT_LOG_NAME).expanduser()

    cleaned: list[str] = raw_argv[:1]
    for argument in raw_argv[1:]:
        if argument == DEBUG_FLAG:
            enabled = True
            continue
        if argument.startswith(DEBUG_LOG_PREFIX):
            enabled = True
            value = argument.removeprefix(DEBUG_LOG_PREFIX).strip()
            if value:
                log_path = Path(value).expanduser()
            continue
        cleaned.append(argument)

    return StartupDebugConfig(enabled=enabled, log_path=log_path, argv=cleaned)


class StartupDebugProbe(QObject):
    """Qt event filter that records top-level widget lifecycle events."""

    def __init__(self, log_path: Path) -> None:
        super().__init__()
        self.log_path = log_path
        self._started = time.perf_counter()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text("", encoding="utf-8")
        self.log("startup-debug enabled")
        self.log(f"log_path={self.log_path.resolve()}")
        self.log(f"python={sys.version.replace(chr(10), ' ')}")
        self.log(f"pid={os.getpid()}")

    def log(self, message: str) -> None:
        """Append one timestamped line to the debug log."""
        elapsed_ms = (time.perf_counter() - self._started) * 1000.0
        wall_time = datetime.now().isoformat(timespec="milliseconds")
        line = f"{wall_time} +{elapsed_ms:9.3f} ms | {message}\n"
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(line)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 - Qt API name.
        """Log top-level widget show/hide/create lifecycle events."""
        event_type = event.type()
        if (
            event_type in _MONITORED_EVENTS
            and isinstance(watched, QWidget)
            and self._should_log_widget_event(watched, event_type)
        ):
            name = _EVENT_NAMES.get(event_type, str(int(event_type)))
            self.log(f"event {name}: {self._widget_summary(watched)}")
        return super().eventFilter(watched, event)

    @staticmethod
    def _should_log_widget_event(widget: QWidget, event_type: QEvent.Type) -> bool:
        """Limit noisy logs to widgets that can explain visible transient windows."""
        if widget.isWindow() or widget.parentWidget() is None:
            return True
        if event_type in {QEvent.Type.Show, QEvent.Type.Hide, QEvent.Type.WinIdChange}:
            return widget.window() is widget
        return False

    def snapshot(self, label: str) -> None:
        """Log the current QApplication top-level widget list."""
        app = QApplication.instance()
        if app is None:
            self.log(f"snapshot {label}: no QApplication instance")
            return
        widgets = app.topLevelWidgets()
        self.log(f"snapshot {label}: top_level_count={len(widgets)}")
        for index, widget in enumerate(widgets):
            self.log(f"  top[{index}]: {self._widget_summary(widget)}")

    @staticmethod
    def _widget_summary(widget: QWidget) -> str:
        geometry = widget.geometry()
        parent = widget.parentWidget()
        flags = int(widget.windowFlags())
        return (
            f"class={type(widget).__name__} "
            f"objectName={widget.objectName()!r} "
            f"title={widget.windowTitle()!r} "
            f"isWindow={widget.isWindow()} "
            f"visible={widget.isVisible()} "
            f"hidden={widget.isHidden()} "
            f"size={geometry.width()}x{geometry.height()} "
            f"pos={geometry.x()},{geometry.y()} "
            f"parent={type(parent).__name__ if parent is not None else None} "
            f"flags=0x{flags:x}"
        )


def install_startup_debug_probe(app: QApplication, log_path: Path) -> StartupDebugProbe:
    """Install the probe and schedule a few startup snapshots."""
    probe = StartupDebugProbe(log_path)
    app.installEventFilter(probe)
    probe.snapshot("after-install")

    for delay_ms in (0, 25, 50, 100, 250, 500, 1000, 2000):
        QTimer.singleShot(
            delay_ms,
            lambda label=f"timer-{delay_ms}ms", active_probe=probe: active_probe.snapshot(label),
        )
    return probe


__all__ = [
    "DEBUG_FLAG",
    "DEBUG_LOG_PREFIX",
    "DEFAULT_LOG_NAME",
    "ENV_ENABLE",
    "ENV_LOG",
    "StartupDebugConfig",
    "StartupDebugProbe",
    "install_startup_debug_probe",
    "parse_startup_debug_args",
]
