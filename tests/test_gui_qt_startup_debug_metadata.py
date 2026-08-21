from __future__ import annotations

from pathlib import Path


def test_qt_startup_debug_module_supports_cli_and_environment_flags():
    content = Path("dpo4000_utils/gui_qt/startup_debug.py").read_text(encoding="utf-8")

    assert 'DEBUG_FLAG = "--startup-debug"' in content
    assert 'DEBUG_LOG_PREFIX = "--startup-debug-log="' in content
    assert 'ENV_ENABLE = "DPO4000_QT_STARTUP_DEBUG"' in content
    assert 'ENV_LOG = "DPO4000_QT_STARTUP_LOG"' in content
    assert 'DEFAULT_LOG_NAME = "dpo4000_qt_startup_debug.log"' in content
    assert "def parse_startup_debug_args" in content
    assert "StartupDebugConfig" in content
    assert "enabled = True" in content
    assert "cleaned.append(argument)" in content


def test_qt_startup_debug_probe_logs_top_level_widget_events_and_snapshots():
    content = Path("dpo4000_utils/gui_qt/startup_debug.py").read_text(encoding="utf-8")

    assert "class StartupDebugProbe(QObject)" in content
    assert "def eventFilter" in content
    assert "QEvent.Type.Show" in content
    assert "QEvent.Type.Hide" in content
    assert "QEvent.Type.Create" in content
    assert "QEvent.Type.ParentChange" in content
    assert "QEvent.Type.WinIdChange" in content
    assert "widget.isWindow()" in content
    assert "widget.parentWidget() is None" in content
    assert "def snapshot" in content
    assert "topLevelWidgets()" in content
    assert "def _widget_summary" in content
    assert "windowTitle()" in content
    assert "windowFlags()" in content
    assert "geometry()" in content


def test_qt_startup_debug_probe_schedules_timed_snapshots():
    content = Path("dpo4000_utils/gui_qt/startup_debug.py").read_text(encoding="utf-8")

    assert "def install_startup_debug_probe" in content
    assert "app.installEventFilter(probe)" in content
    assert "probe.snapshot(\"after-install\")" in content
    assert "QTimer.singleShot" in content
    assert "timer-0ms" in content
    assert "timer-1000ms" in content
    assert "timer-2000ms" in content


def test_qt_runner_wires_startup_debug_before_window_construction():
    content = Path("dpo4000_utils/gui_qt/runner.py").read_text(encoding="utf-8")

    assert "parse_startup_debug_args" in content
    assert "install_startup_debug_probe" in content
    assert "startup_debug = parse_startup_debug_args(sys.argv)" in content
    assert "app = QApplication(startup_debug.argv)" in content
    assert "install_startup_debug_probe(app, startup_debug.log_path)" in content
    assert "before-window-construction" in content
    assert "after-window-construction-before-show" in content
    assert "main window show() called" in content
    assert "after-main-window-show" in content
    assert "app._dpo4000_startup_debug_probe" in content
