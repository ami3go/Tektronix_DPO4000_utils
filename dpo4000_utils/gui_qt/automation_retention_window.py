"""A9 safe file-retention controls and runtime integration."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from ..automation import AutomationState
from ..automation.retention import (
    RetentionError,
    RetentionPlan,
    RetentionPolicy,
    apply_retention_plan,
    load_retention_index,
    plan_retention,
    register_retention_event,
)
from .automation_limits_review_window import QtScopeWindow as AutomationA8ReviewedQtScopeWindow
from .automation_measurement_window import MEASUREMENT_LOGGER_MODE
from .automation_window import FILE_PAGE_INDEX

_GIB = 1024**3
_DAY_S = 24.0 * 60.0 * 60.0


class QtScopeWindow(AutomationA8ReviewedQtScopeWindow):
    """A8 reviewed window extended with owned-artifact retention."""

    def __init__(self, *args, **kwargs) -> None:
        self._retention_run_id = ""
        self._retention_root_active: Path | None = None
        self._retention_seen_paths: set[str] = set()
        self._retention_preview_ack = False
        self._retention_last_plan: RetentionPlan | None = None
        self._retention_last_reclaimed = 0
        self._retention_stop_reason = ""
        super().__init__(*args, **kwargs)

    # ------------------------------------------------------------------
    # Retention UI
    # ------------------------------------------------------------------
    def _build_automation_output_card(self):
        card = self._card("Output & Retention")
        layout = QVBoxLayout(card)
        summary = QLabel(
            "Automation artifacts use the File-page destination/naming settings. A9 deletes only "
            "completed artifacts recorded in its persistent ownership index; unregistered files are never deleted."
        )
        summary.setWordWrap(True)
        layout.addWidget(summary)

        form = QFormLayout()
        self._prepare_form(form)
        self.automation_retention_count_enabled = QCheckBox("Keep last events")
        self.automation_retention_count_enabled.setChecked(True)
        self.automation_retention_count = QSpinBox()
        self.automation_retention_count.setRange(1, 1_000_000)
        self.automation_retention_count.setValue(1000)

        self.automation_retention_size_enabled = QCheckBox("Maximum automation storage")
        self.automation_retention_size_enabled.setChecked(True)
        self.automation_retention_size_gb = QDoubleSpinBox()
        self.automation_retention_size_gb.setRange(0.01, 100000.0)
        self.automation_retention_size_gb.setDecimals(2)
        self.automation_retention_size_gb.setValue(20.0)
        self.automation_retention_size_gb.setSuffix(" GB")

        self.automation_retention_age_enabled = QCheckBox("Delete older than")
        self.automation_retention_age_enabled.setChecked(True)
        self.automation_retention_age_days = QDoubleSpinBox()
        self.automation_retention_age_days.setRange(0.01, 3650.0)
        self.automation_retention_age_days.setDecimals(1)
        self.automation_retention_age_days.setValue(14.0)
        self.automation_retention_age_days.setSuffix(" days")

        self.automation_retention_free_enabled = QCheckBox("Minimum free disk")
        self.automation_retention_free_enabled.setChecked(True)
        self.automation_retention_free_gb = QDoubleSpinBox()
        self.automation_retention_free_gb.setRange(0.01, 100000.0)
        self.automation_retention_free_gb.setDecimals(2)
        self.automation_retention_free_gb.setValue(2.0)
        self.automation_retention_free_gb.setSuffix(" GB")

        self.automation_retention_preview_button = QPushButton("Preview retention")
        self.automation_retention_preview_button.clicked.connect(self.preview_retention_policy)
        self.automation_retention_auto = QCheckBox("Enable automatic deletion")
        self.automation_retention_auto.setChecked(False)
        self.automation_retention_auto.setEnabled(False)
        self.automation_retention_status = QLabel("Preview required before automatic deletion can be enabled.")
        self.automation_retention_status.setWordWrap(True)
        self.automation_retention_reclaimed = QLabel("0 B")

        form.addRow(self.automation_retention_count_enabled, self.automation_retention_count)
        form.addRow(self.automation_retention_size_enabled, self.automation_retention_size_gb)
        form.addRow(self.automation_retention_age_enabled, self.automation_retention_age_days)
        form.addRow(self.automation_retention_free_enabled, self.automation_retention_free_gb)
        form.addRow(self.automation_retention_preview_button)
        form.addRow(self.automation_retention_auto)
        form.addRow("Preview/status", self.automation_retention_status)
        form.addRow("Last reclaimed", self.automation_retention_reclaimed)
        layout.addLayout(form)

        for control in (
            self.automation_retention_count_enabled,
            self.automation_retention_count,
            self.automation_retention_size_enabled,
            self.automation_retention_size_gb,
            self.automation_retention_age_enabled,
            self.automation_retention_age_days,
            self.automation_retention_free_enabled,
            self.automation_retention_free_gb,
        ):
            if hasattr(control, "toggled"):
                control.toggled.connect(self._retention_policy_changed)
            if hasattr(control, "valueChanged"):
                control.valueChanged.connect(self._retention_policy_changed)
        return self._prepare_drawer_card(card)

    def _retention_policy_changed(self, *_args) -> None:
        self._retention_preview_ack = False
        auto = getattr(self, "automation_retention_auto", None)
        if auto is not None:
            auto.setChecked(False)
            auto.setEnabled(False)
        label = getattr(self, "automation_retention_status", None)
        if label is not None:
            label.setText("Policy changed. Preview again before automatic deletion can be enabled.")

    def _retention_policy(self) -> RetentionPolicy:
        keep = (
            int(self.automation_retention_count.value())
            if self.automation_retention_count_enabled.isChecked()
            else None
        )
        max_bytes = (
            int(round(float(self.automation_retention_size_gb.value()) * _GIB))
            if self.automation_retention_size_enabled.isChecked()
            else None
        )
        max_age_s = (
            float(self.automation_retention_age_days.value()) * _DAY_S
            if self.automation_retention_age_enabled.isChecked()
            else None
        )
        min_free = (
            int(round(float(self.automation_retention_free_gb.value()) * _GIB))
            if self.automation_retention_free_enabled.isChecked()
            else None
        )
        return RetentionPolicy(
            keep_last_events=keep,
            max_bytes=max_bytes,
            max_age_s=max_age_s,
            min_free_bytes=min_free,
        )

    def _current_retention_root(self) -> Path:
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        root = Path(self.output_folder.text()).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        return root.resolve()

    def _retention_protected_paths(self) -> tuple[Path, ...]:
        if self._automation_mode() == MEASUREMENT_LOGGER_MODE and self._automation_any_active():
            path = getattr(self, "_measurement_log_path", None)
            if path is not None and Path(path).exists():
                return (Path(path),)
        return ()

    def preview_retention_policy(self) -> None:
        try:
            root = self._current_retention_root()
            plan = plan_retention(
                root,
                self._retention_policy(),
                protected_paths=self._retention_protected_paths(),
            )
        except Exception as exc:  # noqa: BLE001 - exact safety feedback.
            self._message("Retention preview", str(exc), error=True)
            return
        self._retention_last_plan = plan
        self._retention_preview_ack = True
        self.automation_retention_auto.setEnabled(True)
        diagnostics = f"; {' '.join(plan.diagnostics)}" if plan.diagnostics else ""
        self.automation_retention_status.setText(
            f"Tracks {plan.tracked_events} event(s), {plan.tracked_bytes / _GIB:.3f} GB; "
            f"would delete {len(plan.deletions)} event(s) and reclaim "
            f"{plan.bytes_to_reclaim / _GIB:.3f} GB{diagnostics}"
        )

    # ------------------------------------------------------------------
    # Runtime ownership/retention
    # ------------------------------------------------------------------
    def _new_retention_run(self) -> None:
        self._retention_run_id = (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
            + "-"
            + uuid.uuid4().hex[:8]
        )
        self._retention_root_active = self._current_retention_root()
        self._retention_seen_paths = set()
        for path in (
            getattr(self, "_automation_last_path", None),
            getattr(self, "_automation_last_csv_path", None),
        ):
            if path is not None:
                self._retention_seen_paths.add(str(Path(path).resolve(strict=False)))
        self._retention_stop_reason = ""

    def _retention_root_matches_snapshot(self) -> bool:
        active = self._retention_root_active
        if active is None:
            return True
        try:
            return self._current_retention_root() == active
        except Exception:
            return False

    def _retention_stop_safely(self, reason: str) -> None:
        self._retention_stop_reason = str(reason)
        self._append_log(f"Automation A9 safety stop: {reason}")
        self.stop_automation()
        self.statusBar().showMessage(f"Automation stopped: {reason}")

    def _retention_pre_event_guard(self) -> bool:
        if not self._automation_any_active():
            return True
        if not self._retention_root_matches_snapshot():
            self._retention_stop_safely("Output folder changed during the active automation run")
            return False
        root = self._retention_root_active
        if root is None:
            return True
        try:
            policy = self._retention_policy()
            plan = plan_retention(
                root,
                policy,
                protected_paths=self._retention_protected_paths(),
            )
        except Exception as exc:  # noqa: BLE001 - fail closed.
            self._retention_stop_safely(f"Retention safety validation failed: {exc}")
            return False
        if policy.min_free_bytes is not None and plan.free_bytes < policy.min_free_bytes:
            if self.automation_retention_auto.isChecked() and self._retention_preview_ack:
                if not self._apply_retention_plan(plan):
                    return False
                refreshed = plan_retention(
                    root,
                    policy,
                    protected_paths=self._retention_protected_paths(),
                )
                if refreshed.free_bytes < policy.min_free_bytes:
                    self._retention_stop_safely(
                        "Minimum free-disk threshold cannot be restored by retention"
                    )
                    return False
            else:
                self._retention_stop_safely(
                    "Free disk is below the configured minimum and automatic deletion is disabled"
                )
                return False
        return True

    def _new_artifact_paths(self) -> list[Path]:
        result: list[Path] = []
        for raw in (
            getattr(self, "_automation_last_path", None),
            getattr(self, "_automation_last_csv_path", None),
        ):
            if raw is None:
                continue
            path = Path(raw)
            if not path.exists() or not path.is_file():
                continue
            key = str(path.resolve(strict=False))
            if key in self._retention_seen_paths:
                continue
            self._retention_seen_paths.add(key)
            if all(path.resolve(strict=False) != other.resolve(strict=False) for other in result):
                result.append(path)
        return result

    def _register_completed_artifacts(self, controller_kind: str, success_count: int) -> None:
        if not self._retention_run_id:
            return
        if self._automation_mode() == MEASUREMENT_LOGGER_MODE and self._automation_any_active():
            return
        paths = self._new_artifact_paths()
        if not paths:
            return
        root = self._retention_root_active or self._current_retention_root()
        event_id = f"{self._retention_run_id}:{controller_kind}:{int(success_count):08d}"
        try:
            register_retention_event(root, event_id, paths)
        except Exception as exc:  # noqa: BLE001 - ownership failure stops unattended run.
            self._retention_stop_safely(f"Could not register completed artifacts: {exc}")
            return
        self._append_log(
            f"Retention registered {event_id}: {', '.join(path.name for path in paths)}"
        )
        self._apply_retention_after_event()

    def _register_measurement_log_after_stop(self) -> None:
        if not self._retention_run_id:
            return
        path = getattr(self, "_measurement_log_path", None)
        if path is None or not Path(path).exists() or not Path(path).is_file():
            return
        key = str(Path(path).resolve(strict=False))
        if key in self._retention_seen_paths:
            return
        self._retention_seen_paths.add(key)
        root = self._retention_root_active or self._current_retention_root()
        event_id = f"{self._retention_run_id}:measurement-log"
        try:
            register_retention_event(root, event_id, [Path(path)])
            self._append_log(f"Retention registered completed measurement log: {Path(path).name}")
            self._apply_retention_after_event()
        except Exception as exc:  # noqa: BLE001 - log after run is already stopped.
            self._append_log(f"Retention could not register measurement log: {exc}")

    def _apply_retention_plan(self, plan: RetentionPlan) -> bool:
        root = self._retention_root_active or self._current_retention_root()
        try:
            result = apply_retention_plan(root, plan)
        except Exception as exc:  # noqa: BLE001 - fail closed.
            self._retention_stop_safely(f"Retention deletion failed: {exc}")
            return False
        self._retention_last_reclaimed = result.reclaimed_bytes
        for deletion in plan.deletions:
            for relative in deletion.files:
                self._append_log(
                    f"Retention deleted owned artifact: {relative} ({', '.join(deletion.reasons)})"
                )
        self._append_log(
            f"Retention reclaimed {result.reclaimed_bytes} bytes from "
            f"{result.deleted_events} event(s)"
        )
        return True

    def _apply_retention_after_event(self) -> None:
        root = self._retention_root_active or self._current_retention_root()
        try:
            plan = plan_retention(
                root,
                self._retention_policy(),
                protected_paths=self._retention_protected_paths(),
            )
            self._retention_last_plan = plan
        except Exception as exc:  # noqa: BLE001 - ownership/index validation is safety critical.
            self._retention_stop_safely(f"Retention planning failed: {exc}")
            return
        if self.automation_retention_auto.isChecked() and self._retention_preview_ack:
            if plan.deletions and not self._apply_retention_plan(plan):
                return
            if not plan.satisfied:
                self._retention_stop_safely("Retention policy cannot be satisfied safely")
        elif self.automation_retention_free_enabled.isChecked():
            if plan.free_bytes < self._retention_policy().min_free_bytes:
                self._retention_stop_safely(
                    "Minimum free-disk threshold reached while automatic deletion is disabled"
                )
        self._automation_refresh_status()

    def _success_count(self, kind: str) -> int:
        if kind == "trigger":
            return int(self._trigger_controller.statistics.succeeded)
        return int(self._automation_controller.statistics.succeeded)

    def _run_with_retention_registration(self, kind: str, callback) -> None:
        before = self._success_count(kind)
        callback()
        after = self._success_count(kind)
        if after > before:
            self._register_completed_artifacts(kind, after)

    # ------------------------------------------------------------------
    # Mode lifecycle/hooks
    # ------------------------------------------------------------------
    def start_automation(self) -> None:
        try:
            self._new_retention_run()
        except Exception as exc:  # noqa: BLE001 - output-root validation.
            self._message("Automation", f"Retention/output validation failed: {exc}", error=True)
            return
        super().start_automation()
        if not self._automation_any_active():
            self._retention_run_id = ""
            self._retention_root_active = None

    def run_automation_once(self) -> None:
        try:
            self._new_retention_run()
        except Exception as exc:  # noqa: BLE001
            self._message("Automation", f"Retention/output validation failed: {exc}", error=True)
            return
        auto_before = self._success_count("automation")
        trigger_before = self._success_count("trigger")
        super().run_automation_once()
        if self._success_count("trigger") > trigger_before:
            self._register_completed_artifacts("trigger", self._success_count("trigger"))
        elif self._success_count("automation") > auto_before:
            if self._automation_mode() == MEASUREMENT_LOGGER_MODE and not self._automation_any_active():
                self._register_measurement_log_after_stop()
            else:
                self._register_completed_artifacts("automation", self._success_count("automation"))

    def _automation_tick(self) -> None:
        if not self._retention_pre_event_guard():
            return
        self._run_with_retention_registration("automation", super()._automation_tick)

    def _trigger_cycle(self) -> None:
        if not self._retention_pre_event_guard():
            return
        self._run_with_retention_registration("trigger", super()._trigger_cycle)

    def _trigger_bundle_cycle(self) -> None:
        if not self._retention_pre_event_guard():
            return
        self._run_with_retention_registration("trigger", super()._trigger_bundle_cycle)

    def _automation_burst_event(self) -> None:
        if not self._retention_pre_event_guard():
            return
        self._run_with_retention_registration("automation", super()._automation_burst_event)

    def stop_automation(self) -> None:
        was_measurement = self._automation_mode() == MEASUREMENT_LOGGER_MODE
        was_active = self._automation_any_active()
        super().stop_automation()
        if was_measurement and was_active:
            self._register_measurement_log_after_stop()
        if self._retention_stop_reason:
            self.statusBar().showMessage(f"Automation stopped: {self._retention_stop_reason}")

    def _automation_refresh_status(self) -> None:
        super()._automation_refresh_status()
        if not hasattr(self, "automation_retention_status"):
            return
        self.automation_retention_reclaimed.setText(f"{self._retention_last_reclaimed} B")
        editable = not self._automation_any_active() and not bool(
            getattr(self, "_operation_active", False)
        )
        for name in (
            "automation_retention_count_enabled",
            "automation_retention_count",
            "automation_retention_size_enabled",
            "automation_retention_size_gb",
            "automation_retention_age_enabled",
            "automation_retention_age_days",
            "automation_retention_free_enabled",
            "automation_retention_free_gb",
            "automation_retention_preview_button",
        ):
            control = getattr(self, name, None)
            if control is not None:
                control.setEnabled(editable)
        self.automation_retention_auto.setEnabled(editable and self._retention_preview_ack)


__all__ = ["QtScopeWindow"]
