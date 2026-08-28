from __future__ import annotations

from pathlib import Path


def test_qt_startup_debug_module_supports_cli_and_environment_flags():
    content = Path("dpo4000_utils/gui_qt/startup_debug.py").read_text(encoding="utf-8")

    assert 'DEBUG_FLAG = "--startup-debug"' in content
    assert 'DEBUG_LOG_PREFIX = "--startup-debug-log="' in content
    assert 'ENV_ENABLE = "DPO4000_QT_STARTUP_DEBUG"' in content
    assert 'ENV_LOG = "DPO4000_QT_STARTUP_LOG"' in content
    assert "def parse_startup_debug_args" in content
    assert "StartupDebugConfig" in content


def test_qt_startup_debug_probe_logs_top_level_widget_events_and_snapshots():
    content = Path("dpo4000_utils/gui_qt/startup_debug.py").read_text(encoding="utf-8")

    assert "class StartupDebugProbe(QObject)" in content
    assert "def eventFilter" in content
    assert "QEvent.Type.Show" in content
    assert "QEvent.Type.Hide" in content
    assert "QEvent.Type.WinIdChange" in content
    assert "widget.isWindow()" in content
    assert "def snapshot" in content
    assert "topLevelWidgets()" in content
    assert "def _widget_summary" in content


def test_qt_startup_debug_probe_schedules_timed_snapshots():
    content = Path("dpo4000_utils/gui_qt/startup_debug.py").read_text(encoding="utf-8")

    assert "def install_startup_debug_probe" in content
    assert "app.installEventFilter(probe)" in content
    assert 'probe.snapshot("after-install")' in content
    assert "for delay_ms in (0, 25, 50, 100, 250, 500, 1000, 2000):" in content
    assert "QTimer.singleShot(" in content
    assert 'lambda label=f"timer-{delay_ms}ms"' in content


def test_qt_runner_wires_startup_debug_and_startup_check():
    content = Path("dpo4000_utils/gui_qt/runner.py").read_text(encoding="utf-8")

    assert 'STARTUP_CHECK_FLAG = "--startup-check"' in content
    assert "parse_startup_debug_args" in content
    assert "install_startup_debug_probe" in content
    assert "before-window-construction" in content
    assert "after-window-construction-before-show" in content
    assert "after-main-window-show" in content
    assert "QTimer.singleShot(2500, app.quit)" in content


def test_qt_startup_check_script_runs_runner_with_debug_and_auto_close():
    content = Path("scripts/qt_startup_check.py").read_text(encoding="utf-8")

    assert "dpo4000_utils.gui_qt.runner" in content
    assert "--startup-debug" in content
    assert "--startup-debug-log=" in content
    assert "--startup-check" in content
    assert "subprocess.run" in content
