"""A11 automatic transport recovery for Automation scope actions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QFormLayout, QLabel, QSpinBox

from ..automation.recovery import RecoveryPolicy, RecoveryStatistics
from ..errors import is_transport_error
from .automation_profiles_review_window import QtScopeWindow as AutomationA10ReviewedQtScopeWindow
from .scope_worker import WorkerResult

_REPLAY_SAFE_PREFIXES = (
    "Automation image #",
    "Automation waveform CSV #",
    "Logging measurement row #",
    "Waiting for triggered acquisition #",
    "Saving triggered image #",
)


class QtScopeWindow(AutomationA10ReviewedQtScopeWindow):
    """A10 reviewed window extended with bounded A11 reconnect/retry behavior."""

    def __init__(self, *args, **kwargs) -> None:
        self._recovery_statistics = RecoveryStatistics()
        super().__init__(*args, **kwargs)

    def _build_automation_reliability_card(self):
        card = self._card("Reliability")
        form = QFormLayout(card)
        self._prepare_form(form)
        self.automation_reconnect_enabled = QCheckBox("Automatic reconnect on transport failure")
        self.automation_reconnect_enabled.setChecked(True)
        self.automation_reconnect_retries = QSpinBox()
        self.automation_reconnect_retries.setRange(0, 20)
        self.automation_reconnect_retries.setValue(2)
        self.automation_reconnect_delay = QDoubleSpinBox()
        self.automation_reconnect_delay.setRange(0.1, 300.0)
        self.automation_reconnect_delay.setDecimals(1)
        self.automation_reconnect_delay.setValue(1.0)
        self.automation_reconnect_delay.setSuffix(" s")
        self.automation_reconnect_max_failures = QSpinBox()
        self.automation_reconnect_max_failures.setRange(1, 1000)
        self.automation_reconnect_max_failures.setValue(5)
        hint = QLabel(
            "Only classified transport failures are retried. Evidence bundles/conditional and "
            "other non-replay-safe operations fail closed rather than blindly duplicating an event."
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        form.addRow(self.automation_reconnect_enabled)
        form.addRow("Retries per safe event", self.automation_reconnect_retries)
        form.addRow("Base retry delay", self.automation_reconnect_delay)
        form.addRow("Stop after consecutive failures", self.automation_reconnect_max_failures)
        form.addRow(hint)
        return self._prepare_drawer_card(card)

    def _build_automation_current_run_card(self):
        card = super()._build_automation_current_run_card()
        form = card.layout()
        if isinstance(form, QFormLayout):
            self.automation_retry_count_label = QLabel("0")
            self.automation_reconnect_count_label = QLabel("0")
            self.automation_transport_failure_label = QLabel("0")
            form.addRow("Retry attempts", self.automation_retry_count_label)
            form.addRow("Reconnects", self.automation_reconnect_count_label)
            form.addRow("Transport failures", self.automation_transport_failure_label)
        return card

    def _selected_recovery_policy(self) -> RecoveryPolicy:
        return RecoveryPolicy(
            enabled=self.automation_reconnect_enabled.isChecked(),
            max_retries=int(self.automation_reconnect_retries.value()),
            retry_delay_s=float(self.automation_reconnect_delay.value()),
            max_consecutive_failures=int(self.automation_reconnect_max_failures.value()),
        )

    def _automation_refresh_status(self) -> None:
        super()._automation_refresh_status()
        stats = self._recovery_statistics
        for name, value in (
            ("automation_retry_count_label", stats.retry_attempts),
            ("automation_reconnect_count_label", stats.reconnects),
            ("automation_transport_failure_label", stats.transport_failures),
        ):
            label = getattr(self, name, None)
            if label is not None:
                label.setText(str(value))
        editable = not self._automation_any_active() and not bool(
            getattr(self, "_operation_active", False)
        )
        for name in (
            "automation_reconnect_enabled",
            "automation_reconnect_retries",
            "automation_reconnect_delay",
            "automation_reconnect_max_failures",
        ):
            control = getattr(self, name, None)
            if control is not None:
                control.setEnabled(editable)

    def _collect_automation_profile_config(self) -> dict:
        config = super()._collect_automation_profile_config()
        config["recovery"] = {
            "enabled": self.automation_reconnect_enabled.isChecked(),
            "max_retries": int(self.automation_reconnect_retries.value()),
            "retry_delay_s": float(self.automation_reconnect_delay.value()),
            "max_consecutive_failures": int(self.automation_reconnect_max_failures.value()),
        }
        return config

    def _preflight_automation_profile_config(self, config: dict) -> None:
        super()._preflight_automation_profile_config(config)
        recovery = config.get("recovery", {})
        if recovery is None:
            return
        if not isinstance(recovery, dict):
            raise ValueError("Automation recovery profile section must be an object.")
        if recovery:
            RecoveryPolicy(
                enabled=recovery.get("enabled", True),
                max_retries=recovery.get("max_retries", 2),
                retry_delay_s=recovery.get("retry_delay_s", 1.0),
                max_consecutive_failures=recovery.get("max_consecutive_failures", 5),
            )

    def _apply_automation_profile_config(self, config: dict) -> None:
        super()._apply_automation_profile_config(config)
        recovery = config.get("recovery", {})
        if not isinstance(recovery, dict) or not recovery:
            return
        policy = RecoveryPolicy(
            enabled=recovery.get("enabled", True),
            max_retries=recovery.get("max_retries", 2),
            retry_delay_s=recovery.get("retry_delay_s", 1.0),
            max_consecutive_failures=recovery.get("max_consecutive_failures", 5),
        )
        self.automation_reconnect_enabled.setChecked(policy.enabled)
        self.automation_reconnect_retries.setValue(policy.max_retries)
        self.automation_reconnect_delay.setValue(policy.retry_delay_s)
        self.automation_reconnect_max_failures.setValue(policy.max_consecutive_failures)

    def _execute_scope_action_once(
        self,
        resource: str,
        timeout_ms: int,
        callback: Callable[[Any], object],
    ) -> WorkerResult:
        keep = getattr(self, "keep_session", None)
        if keep is not None and keep.isChecked():
            return self._persistent_session_manager().execute(resource, timeout_ms, callback)
        return super()._execute_scope_action_once(resource, timeout_ms, callback)

    def _recovery_wait(self, seconds: float) -> None:
        loop = QEventLoop(self)
        QTimer.singleShot(max(1, int(round(float(seconds) * 1000.0))), loop.quit)
        loop.exec()

    def _recovery_replay_safe(self, description: str) -> bool:
        return any(str(description).startswith(prefix) for prefix in _REPLAY_SAFE_PREFIXES)

    def _invalidate_transport_session(self) -> None:
        if getattr(self, "_persistent_scope_session", None) is not None:
            self._release_persistent_scope_session(log=False)

    def _verified_retry_callback(self, callback, expected_idn: str):
        def wrapped(scope):
            identity = str(scope.query_identity()).strip()
            if expected_idn and identity != expected_idn:
                raise RuntimeError(
                    f"Reconnected scope identity changed: expected {expected_idn!r}, got {identity!r}."
                )
            return callback(scope)

        return wrapped

    def _run_action(self, description: str, callback: Callable[[Any], object]) -> object | None:
        """Run one action with bounded retry for replay-safe transport failures only."""
        self._operation_active = True
        self._last_action = description
        self.statusBar().showMessage(description)
        self._append_log(description)
        self._update_scope_control_enabled()
        self._update_status_strip()
        keep = getattr(self, "keep_session", None)
        if keep is not None:
            keep.setEnabled(False)
        try:
            try:
                resource = self._selected_resource()
                timeout_ms = self._timeout()
                policy = self._selected_recovery_policy()
            except Exception as exc:  # noqa: BLE001 - exact validation failure.
                return self._finish_non_transport_action_error(description, exc)

            expected_idn = str(getattr(self, "_last_idn", "") or "").strip()
            if expected_idn.startswith("Error:"):
                expected_idn = ""
            replay_safe = self._recovery_replay_safe(description)
            last_error: BaseException | None = None
            total_attempts = 1 + (policy.max_retries if policy.enabled and replay_safe else 0)

            for attempt in range(total_attempts):
                attempt_callback = (
                    self._verified_retry_callback(callback, expected_idn) if attempt else callback
                )
                result = self._execute_scope_action_once(resource, timeout_ms, attempt_callback)
                if result.error is None:
                    if attempt:
                        self._recovery_statistics.note_reconnect_success()
                        self._append_log(
                            f"Automation A11 reconnect successful after {attempt} retry attempt(s)"
                        )
                    else:
                        self._recovery_statistics.note_normal_success()
                    return self._finish_scope_action_success(description, result.value)

                error = result.error
                last_error = error
                if not is_transport_error(error):
                    return self._finish_non_transport_action_error(description, error)

                self._recovery_statistics.note_transport_failure(error)
                self._invalidate_transport_session()
                if not policy.enabled or not replay_safe or attempt >= total_attempts - 1:
                    break

                retry_number = attempt + 1
                self._recovery_statistics.note_retry()
                delay = policy.delay_for_attempt(retry_number)
                self._append_log(
                    f"Automation A11 transport failure; retry {retry_number}/{policy.max_retries} "
                    f"after {delay:g} s: {error}"
                )
                self.statusBar().showMessage(
                    f"Recovering scope connection ({retry_number}/{policy.max_retries})"
                )
                self._recovery_wait(delay)

            assert last_error is not None
            self._recovery_statistics.note_exhausted(last_error)
            consecutive = self._recovery_statistics.consecutive_failures
            result = self._finish_scope_action_error(description, last_error)
            if (
                policy.enabled
                and consecutive >= policy.max_consecutive_failures
                and self._automation_any_active()
            ):
                self._append_log(
                    f"Automation A11 stopping after {consecutive} consecutive transport failures"
                )
                self.stop_automation()
            return result
        finally:
            if keep is not None:
                keep.setEnabled(True)
            if getattr(self, "_persistent_session_dirty", False):
                self._release_persistent_scope_session()


__all__ = ["QtScopeWindow"]
