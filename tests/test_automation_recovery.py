from __future__ import annotations

from pathlib import Path

import pytest

from dpo4000_utils.automation.recovery import RecoveryPolicy, RecoveryStatistics


def test_a11_recovery_policy_defaults_and_backoff() -> None:
    policy = RecoveryPolicy()
    assert policy.enabled is True
    assert policy.max_retries == 2
    assert policy.delay_for_attempt(1) == 1.0
    assert policy.delay_for_attempt(2) == 2.0
    with pytest.raises(ValueError):
        RecoveryPolicy(max_retries=-1)
    with pytest.raises(ValueError):
        RecoveryPolicy(retry_delay_s=0.0)
    with pytest.raises(ValueError):
        RecoveryPolicy(max_consecutive_failures=0)


def test_a11_statistics_reset_only_after_success() -> None:
    stats = RecoveryStatistics()
    stats.note_transport_failure("lost")
    stats.note_retry()
    stats.note_exhausted("lost")
    assert stats.transport_failures == 1
    assert stats.retry_attempts == 1
    assert stats.consecutive_failures == 1
    stats.note_reconnect_success()
    assert stats.reconnects == 1
    assert stats.consecutive_failures == 0


def test_a11_gui_uses_shared_action_gateway_and_fail_closed_replay_policy() -> None:
    root = Path(__file__).resolve().parents[1]
    recovery = (root / "dpo4000_utils" / "gui_qt" / "automation_recovery_window.py").read_text(
        encoding="utf-8"
    )
    stable = (root / "dpo4000_utils" / "gui_qt" / "stable_window.py").read_text(
        encoding="utf-8"
    )
    assert "_execute_scope_action_once" in stable
    assert "super()._execute_scope_action_once" in recovery
    assert "is_transport_error" in recovery
    assert "_REPLAY_SAFE_PREFIXES" in recovery
    assert "Capturing triggered image + CSV" not in recovery.split("_REPLAY_SAFE_PREFIXES", 1)[1].split(")", 1)[0]
    assert "scope.query_identity()" in recovery
    assert ".query(" not in recovery
    assert ".write(" not in recovery
