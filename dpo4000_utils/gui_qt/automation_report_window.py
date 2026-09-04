"""Automation A12 durable run/event reporting UI integration."""

from __future__ import annotations

from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QFormLayout, QLabel

from ..automation.reporting import AutomationRunReporter, make_event_record
from .automation_recovery_review_window import QtScopeWindow as AutomationA11ReviewedQtScopeWindow
from .automation_window import FILE_PAGE_INDEX

_REPORT_OPERATION_PREFIXES = (
    "Automation image #",
    "Automation waveform CSV #",
    "Logging measurement row #",
    "Waiting for triggered acquisition #",
    "Saving triggered image #",
    "Capturing triggered image + CSV #",
    "Evaluating conditional capture #",
    "Burst capture #",
)


def _package_version() -> str:
    try:
        return version("dpo4000-utils")
    except PackageNotFoundError:
        return "source-tree"


def _paths_from_result(result: Any) -> tuple[str, ...]:
    paths: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, Path):
            text = str(value)
            if text not in seen:
                seen.add(text)
                paths.append(text)
            return
        if isinstance(value, str):
            candidate = Path(value)
            if candidate.suffix.lower() in {".png", ".csv", ".json", ".dpo4log"}:
                text = str(candidate)
                if text not in seen:
                    seen.add(text)
                    paths.append(text)
            return
        for attr in ("image_path", "csv_path", "path"):
            if hasattr(value, attr):
                add(getattr(value, attr))
        if hasattr(value, "artifacts"):
            add(getattr(value, "artifacts"))

    add(result)
    return tuple(paths)


class QtScopeWindow(AutomationA11ReviewedQtScopeWindow):
    """A11 reviewed window extended with crash-tolerant A12 reporting."""

    def __init__(self, *args, **kwargs) -> None:
        self._automation_reporter: AutomationRunReporter | None = None
        self._automation_report_event_sequence = 0
        self._automation_report_partial_count = 0
        self._automation_report_in_action = False
        self._automation_report_watchdog: QTimer | None = None
        self._automation_last_report_path: Path | None = None
        super().__init__(*args, **kwargs)
        self._automation_report_watchdog = QTimer(self)
        self._automation_report_watchdog.setInterval(250)
        self._automation_report_watchdog.timeout.connect(self._automation_report_watchdog_tick)

    def _build_automation_current_run_card(self):
        card = super()._build_automation_current_run_card()
        form = card.layout()
        if isinstance(form, QFormLayout):
            self.automation_report_event_count_label = QLabel("0")
            self.automation_report_path_label = QLabel("--")
            self.automation_report_path_label.setWordWrap(True)
            form.addRow("Report events", self.automation_report_event_count_label)
            form.addRow("Run report", self.automation_report_path_label)
        return card

    def _automation_refresh_status(self) -> None:
        super()._automation_refresh_status()
        reporter = self._automation_reporter
        count_label = getattr(self, "automation_report_event_count_label", None)
        path_label = getattr(self, "automation_report_path_label", None)
        if count_label is not None:
            count_label.setText(str(reporter.event_count if reporter is not None else 0))
        if path_label is not None:
            if reporter is not None:
                path_label.setText(str(reporter.summary_path))
            elif self._automation_last_report_path is not None:
                path_label.setText(str(self._automation_last_report_path))
            else:
                path_label.setText("--")

    def _report_root(self) -> Path:
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        root = Path(self.output_folder.text()).expanduser() / "automation_reports"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _begin_automation_report(self) -> None:
        if self._automation_reporter is not None and not self._automation_reporter.finalized:
            return
        try:
            resource = self._selected_resource()
        except Exception:
            resource = ""
        profile_name = ""
        profile_widget = getattr(self, "automation_profile_name", None)
        if profile_widget is not None:
            profile_name = profile_widget.text().strip()
        self._automation_report_event_sequence = 0
        self._automation_report_partial_count = 0
        self._automation_reporter = AutomationRunReporter(
            root=self._report_root(),
            mode=self._automation_mode(),
            config=self._collect_automation_profile_config(),
            resource=resource,
            idn=str(getattr(self, "_last_idn", "") or ""),
            profile_name=profile_name,
            package_version=_package_version(),
        )
        self._append_log(f"Automation A12 report started: {self._automation_reporter.summary_path}")
        self._automation_refresh_status()

    def _automation_operation_cause(self, description: str) -> str:
        text = str(description)
        if "trigger" in text.lower():
            return "scope_trigger"
        if text.startswith("Evaluating conditional"):
            return "measurement_condition"
        if text.startswith("Burst capture"):
            return "burst"
        if text.startswith("Logging measurement"):
            return "periodic_measurement"
        return "periodic_or_manual_run_once"

    def _run_action(self, description, callback):
        reporter = self._automation_reporter
        reportable = reporter is not None and any(
            str(description).startswith(prefix) for prefix in _REPORT_OPERATION_PREFIXES
        )
        if not reportable:
            return super()._run_action(description, callback)

        started = datetime.now(timezone.utc)
        retries_before = self._recovery_statistics.retry_attempts
        self._automation_report_in_action = True
        result = None
        caught: BaseException | None = None
        try:
            result = super()._run_action(description, callback)
            return result
        except BaseException as exc:  # noqa: BLE001 - preserve reporting before re-raise.
            caught = exc
            raise
        finally:
            ended = datetime.now(timezone.utc)
            self._automation_report_in_action = False
            current = self._automation_reporter
            if current is not None and not current.finalized:
                self._automation_report_event_sequence += 1
                artifacts = _paths_from_result(result)
                success = caught is None and result is not None and not str(
                    getattr(self, "_last_action", "")
                ).startswith("Failed:")
                error_text = "" if success else str(getattr(self, "_last_action", "Operation failed"))
                status = "success" if success else ("partial" if artifacts else "failed")
                if status == "partial":
                    self._automation_report_partial_count += 1
                current.append_event(
                    make_event_record(
                        sequence=self._automation_report_event_sequence,
                        description=str(description),
                        cause=self._automation_operation_cause(str(description)),
                        status=status,
                        started_at=started,
                        ended_at=ended,
                        retry_count=max(0, self._recovery_statistics.retry_attempts - retries_before),
                        artifact_paths=artifacts,
                        error=caught,
                        error_text=error_text,
                    )
                )
                self._automation_refresh_status()
            if self._automation_reporter is not None and not self._automation_any_active():
                self._finalize_automation_report("operation_completed")

    def _report_counters(self) -> dict[str, int]:
        auto = self._automation_controller.statistics
        trigger = self._trigger_controller.statistics
        return {
            "attempted": int(auto.attempted + trigger.attempted),
            "succeeded": int(auto.succeeded + trigger.succeeded),
            "skipped": int(auto.skipped + trigger.skipped),
            "failed": int(auto.failed + trigger.failed),
            "partial": int(self._automation_report_partial_count),
        }

    def _finalize_automation_report(self, stop_reason: str) -> None:
        reporter = self._automation_reporter
        if reporter is None or reporter.finalized:
            return
        recovery = self._recovery_statistics
        retention_plan = getattr(self, "_retention_last_plan", None)
        retention = {
            "last_reclaimed_bytes": int(getattr(self, "_retention_last_reclaimed", 0)),
            "planned_deletions": len(retention_plan.deletions) if retention_plan is not None else 0,
        }
        final_error = (
            str(getattr(self._automation_controller.statistics, "last_error", ""))
            or str(getattr(self._trigger_controller.statistics, "last_error", ""))
            or recovery.last_error
        )
        path = reporter.finalize(
            stop_reason=stop_reason,
            counters=self._report_counters(),
            recovery={
                "retry_attempts": recovery.retry_attempts,
                "reconnects": recovery.reconnects,
                "transport_failures": recovery.transport_failures,
                "consecutive_failures": recovery.consecutive_failures,
            },
            retention=retention,
            final_error=final_error,
        )
        self._automation_last_report_path = path
        self._append_log(f"Automation A12 report finalized: {path}")
        watchdog = self._automation_report_watchdog
        if watchdog is not None:
            watchdog.stop()
        self._automation_refresh_status()

    def _automation_report_watchdog_tick(self) -> None:
        if self._automation_reporter is None:
            return
        if not self._automation_any_active() and not self._automation_report_in_action:
            reason = (
                str(getattr(self, "_run_limit_stop_reason", ""))
                or str(getattr(self, "_retention_stop_reason", ""))
                or "natural_completion"
            )
            self._finalize_automation_report(reason)

    def start_automation(self) -> None:
        self._begin_automation_report()
        super().start_automation()
        if self._automation_any_active():
            self._automation_report_watchdog.start()
        else:
            self._finalize_automation_report("start_rejected_or_completed")

    def run_automation_once(self) -> None:
        self._begin_automation_report()
        super().run_automation_once()
        if self._automation_any_active():
            self._automation_report_watchdog.start()
        elif not self._automation_report_in_action:
            self._finalize_automation_report("run_once_complete")

    def stop_automation(self) -> None:
        super().stop_automation()
        if not self._automation_report_in_action:
            reason = (
                str(getattr(self, "_run_limit_stop_reason", ""))
                or str(getattr(self, "_retention_stop_reason", ""))
                or "user_stop"
            )
            self._finalize_automation_report(reason)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API name.
        self._finalize_automation_report("application_close")
        super().closeEvent(event)


__all__ = ["QtScopeWindow"]
