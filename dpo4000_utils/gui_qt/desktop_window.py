"""Final desktop presentation policy for DPO4000 Desk.

This layer intentionally contains no instrument implementation.  It specializes
the API-only Qt window with non-modal connection feedback so routine *IDN?
connection checks never interrupt the operator with message boxes.
"""

from __future__ import annotations

from .api_window import QtScopeWindow as ApiQtScopeWindow

CONNECTION_TEST_DESCRIPTION = "Testing scope connection"


class QtScopeWindow(ApiQtScopeWindow):
    """Launched desktop window with status-only connection feedback."""

    def test_connection(self) -> None:
        """Test the selected scope and report the result without modal dialogs."""
        result = self._run_action(
            CONNECTION_TEST_DESCRIPTION,
            lambda scope: scope.query_identity(),
        )
        if result is None:
            return

        idn = str(result).strip()
        self._last_idn = idn
        self._connection_ok = True
        self._last_action = "IDN OK"
        self._update_scope_control_enabled()
        self._update_status_strip()
        self.statusBar().showMessage(f"Connected: {idn}")

    def _finish_scope_action_error(self, description: str, exc: BaseException) -> None:
        """Keep connection-test errors non-modal; preserve dialogs for other actions."""
        if description != CONNECTION_TEST_DESCRIPTION:
            return super()._finish_scope_action_error(description, exc)

        error_text = str(exc).strip() or exc.__class__.__name__
        self._connection_ok = False
        self._operation_active = False
        self._last_idn = f"Error: {error_text}"
        self._last_action = f"Connection error: {error_text}"
        self._append_log(f"ERROR: {error_text}")
        self._update_scope_control_enabled()
        self._update_status_strip()
        self.statusBar().showMessage(f"Connection error: {error_text}")
        return None


__all__ = ["CONNECTION_TEST_DESCRIPTION", "QtScopeWindow"]
