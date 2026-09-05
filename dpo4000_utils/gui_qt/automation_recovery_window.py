"""A11 automatic transport recovery for Automation scope actions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QCheckBox, QDoubleSpinBox, QFormLayout, QLabel, QSpinBox

from ..automation.recovery import RecoveryPolicy, RecoveryStatistics
from ..errors import is_transport_error
from .automation_profiles_review_window import QtScopeWindow as AutomationA10ReviewedQtScopeWindow

_REPLAY_SAFE_PREFIXES = (
    "Automation image #",
    "Automation waveform CSV #",
    "Logging measurement row #",
    "Waiting for triggered acquisition #",
    "Saving triggered image #",
)


class QtScopeWindow(AutomationA10ReviewedQtScopeWindow):
    """A10 reviewed window extended with bounded asynchronous reconnect/retry behavior."""

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

    def _recovery_replay_safe(self, description: str) -> bool:
        return any(str(description).startswith(prefix) for prefix in _REPLAY_SAFE_PREFIXES)

    def _verified_retry_callback(self, callback, expected_idn: str):
        def wrapped(scope):
            identity = str(scope.query_identity()).strip()
            if expected_idn and identity != expected_idn:
                raise RuntimeError(
                    f"Reconnected scope identity changed: expected {expected_idn!r}, got {identity!r}."
                )
            return callback(scope)

        return wrapped

    def _run_action(
        self,
        description: str,
        callback: Callable[[Any], object],
        *,
        on_success: Callable[[object], None] | None = None,
        on_error: Callable[[BaseException], None] | None = None,
        retain_session: bool = False,
    ) -> None:
        """Dispatch one action asynchronously with bounded replay-safe transport recovery.

        Recovery deliberately composes with the production asynchronous scope
        dispatcher instead of owning a second VISA/session implementation. A failed
        transport request invalidates the worker-owned session, and a retry therefore
        reconnects lazily on the same serialized worker thread.
        """
        parent_run_action = super(QtScopeWindow, self)._run_action

        try:
            policy = self._selected_recovery_policy()
        except (AttributeError, RuntimeError):
            # Automation cards may not have been lazy-built yet. Non-Automation GUI
            # actions must still use the production dispatcher without depending on
            # Automation controls being present.
            parent_run_action(
                description,
                callback,
                on_success=on_success,
                on_error=on_error,
                retain_session=retain_session,
            )
            return

        replay_safe = self._recovery_replay_safe(description)
        max_retries = policy.max_retries if policy.enabled and replay_safe else 0
        expected_idn = str(getattr(self, "_last_idn", "") or "").strip()
        if expected_idn in {"Not tested", "Retest required"} or expected_idn.startswith("Error:"):
            expected_idn = ""

        def refresh_statistics() -> None:
            try:
                self._automation_refresh_status()
            except (AttributeError, RuntimeError):
                pass

        def complete_success(value: object, attempt: int) -> None:
            if attempt:
                self._recovery_statistics.note_reconnect_success()
                self._append_log(
                    f"Automation A11 reconnect successful after {attempt} retry attempt(s)"
                )
            else:
                self._recovery_statistics.note_normal_success()
            refresh_statistics()
            if on_success is not None:
                on_success(value)

        def complete_failure(error: BaseException, attempt: int) -> None:
            if not is_transport_error(error):
                refresh_statistics()
                if on_error is not None:
                    on_error(error)
                return

            self._recovery_statistics.note_transport_failure(error)
            if attempt >= max_retries:
                self._recovery_statistics.note_exhausted(error)
                consecutive = self._recovery_statistics.consecutive_failures
                refresh_statistics()
                if (
                    policy.enabled
                    and consecutive >= policy.max_consecutive_failures
                    and self._automation_any_active()
                ):
                    self._append_log(
                        f"Automation A11 stopping after {consecutive} consecutive transport failures"
                    )
                    self.stop_automation()
                if on_error is not None:
                    on_error(error)
                return

            retry_number = attempt + 1
            self._recovery_statistics.note_retry()
            delay = policy.delay_for_attempt(retry_number)
            self._append_log(
                f"Automation A11 transport failure; retry {retry_number}/{max_retries} "
                f"after {delay:g} s: {error}"
            )
            self.statusBar().showMessage(
                f"Recovering scope connection ({retry_number}/{max_retries})"
            )
            refresh_statistics()
            QTimer.singleShot(
                max(1, int(round(delay * 1000.0))),
                lambda: dispatch(retry_number),
            )

        def dispatch(attempt: int) -> None:
            attempt_callback = (
                self._verified_retry_callback(callback, expected_idn) if attempt else callback
            )
            parent_run_action(
                description,
                attempt_callback,
                on_success=lambda value: complete_success(value, attempt),
                on_error=lambda error: complete_failure(error, attempt),
                retain_session=retain_session,
            )

        dispatch(0)


__all__ = ["QtScopeWindow"]
