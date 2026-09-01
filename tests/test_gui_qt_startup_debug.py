"""Startup debug flags and probe, exercised by calling them."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QWidget  # noqa: E402

from dpo4000_utils.gui_qt.startup_debug import (  # noqa: E402
    DEBUG_FLAG,
    DEBUG_LOG_PREFIX,
    ENV_ENABLE,
    ENV_LOG,
    install_startup_debug_probe,
    parse_startup_debug_args,
)


# ----------------------------------------------------------------------
# Flag and environment parsing
# ----------------------------------------------------------------------
def test_debug_is_off_by_default(monkeypatch):
    monkeypatch.delenv(ENV_ENABLE, raising=False)
    monkeypatch.delenv(ENV_LOG, raising=False)

    config = parse_startup_debug_args(["dpo4000-desk"])

    assert not config.enabled
    assert config.argv == ["dpo4000-desk"]


def test_command_line_flag_enables_debug_and_is_consumed(monkeypatch):
    monkeypatch.delenv(ENV_ENABLE, raising=False)

    config = parse_startup_debug_args(["dpo4000-desk", DEBUG_FLAG])

    assert config.enabled
    assert DEBUG_FLAG not in config.argv, "the flag must not reach QApplication"


def test_log_path_can_be_set_on_the_command_line(monkeypatch, tmp_path):
    monkeypatch.delenv(ENV_LOG, raising=False)
    target = tmp_path / "startup.log"

    config = parse_startup_debug_args(["dpo4000-desk", f"{DEBUG_LOG_PREFIX}{target}"])

    assert Path(config.log_path) == target
    assert not any(a.startswith(DEBUG_LOG_PREFIX) for a in config.argv)


def test_environment_variables_enable_debug_and_set_the_log(monkeypatch, tmp_path):
    target = tmp_path / "from_env.log"
    monkeypatch.setenv(ENV_ENABLE, "1")
    monkeypatch.setenv(ENV_LOG, str(target))

    config = parse_startup_debug_args(["dpo4000-desk"])

    assert config.enabled
    assert Path(config.log_path) == target


# ----------------------------------------------------------------------
# Probe behaviour
# ----------------------------------------------------------------------
def test_probe_writes_snapshots_and_widget_events(qt_app, tmp_path):
    log_path = tmp_path / "probe.log"
    probe = install_startup_debug_probe(qt_app, log_path)
    try:
        probe.log("hello")
        widget = QWidget()
        widget.show()
        qt_app.processEvents()
        probe.snapshot("after-show")
        widget.close()
        widget.deleteLater()
        qt_app.processEvents()

        text = log_path.read_text(encoding="utf-8")
        assert "hello" in text
        assert "after-show" in text
        # The install itself records a baseline snapshot.
        assert "after-install" in text
    finally:
        qt_app.removeEventFilter(probe)


def test_probe_records_top_level_window_show_events(qt_app, tmp_path):
    log_path = tmp_path / "events.log"
    probe = install_startup_debug_probe(qt_app, log_path)
    try:
        window = QWidget()
        window.setWindowTitle("ProbeTarget")
        window.show()
        qt_app.processEvents()

        text = log_path.read_text(encoding="utf-8")
        assert "event" in text, "no widget lifecycle events were logged"
    finally:
        window.close()
        window.deleteLater()
        qt_app.removeEventFilter(probe)
        qt_app.processEvents()


def test_probe_log_directory_is_created_on_demand(qt_app, tmp_path):
    log_path = tmp_path / "nested" / "deeper" / "probe.log"
    probe = install_startup_debug_probe(qt_app, log_path)
    try:
        probe.log("created")
        assert log_path.exists()
    finally:
        qt_app.removeEventFilter(probe)
