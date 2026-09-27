"""A18 Evidence Bundle controls for the composed Recipe page."""

from __future__ import annotations

from pathlib import Path
import re
import threading
from typing import Any, Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ....evidence import EvidenceBundleResult, create_evidence_bundle
from ....recipe import RecipeResult
from ....rules import RuleSetResult


def _safe_filename(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._")
    return text or "evidence"


class EvidenceBundlePanel(QWidget):
    """Capture A18 evidence using the existing serialized scope worker."""

    def __init__(
        self,
        *,
        run_action: Callable[..., Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("A18EvidenceBundlePanel")
        self._run_action = run_action
        self._recipe_result: RecipeResult | None = None
        self._rule_result: RuleSetResult | None = None
        self._cancel_event: threading.Event | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(6)

        title = QLabel("A18 Evidence Bundle")
        title.setObjectName("evidenceBundleTitle")
        layout.addWidget(title)

        controls = QHBoxLayout()
        self.screen_checkbox = QCheckBox("Scope PNG")
        self.screen_checkbox.setObjectName("evidenceScreenCheck")
        self.screen_checkbox.setChecked(True)
        self.waveform_checkbox = QCheckBox("Waveforms")
        self.waveform_checkbox.setObjectName("evidenceWaveformCheck")
        self.waveform_checkbox.setChecked(True)
        self.points_combo = QComboBox()
        self.points_combo.setObjectName("evidencePointsCombo")
        for label, value in (
            ("Full", None),
            ("1k", 1_000),
            ("10k", 10_000),
            ("100k", 100_000),
            ("1M", 1_000_000),
        ):
            self.points_combo.addItem(label, value)
        self.points_combo.setCurrentIndex(1)
        self.save_button = QPushButton("Save Evidence…")
        self.save_button.setObjectName("evidenceSaveButton")
        self.cancel_button = QPushButton("Cancel Evidence")
        self.cancel_button.setObjectName("evidenceCancelButton")
        controls.addWidget(self.screen_checkbox)
        controls.addWidget(self.waveform_checkbox)
        controls.addWidget(QLabel("Points:"))
        controls.addWidget(self.points_combo)
        controls.addStretch(1)
        controls.addWidget(self.save_button)
        controls.addWidget(self.cancel_button)
        layout.addLayout(controls)

        self.status_label = QLabel("Run a recipe to enable evidence capture.")
        self.status_label.setObjectName("evidenceStatusLabel")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.save_button.clicked.connect(self._save_clicked)
        self.cancel_button.clicked.connect(self._cancel_clicked)
        self.save_button.setEnabled(False)
        self.cancel_button.setEnabled(False)

    def set_result(
        self,
        recipe_result: RecipeResult,
        rule_result: RuleSetResult | None = None,
    ) -> None:
        self._recipe_result = recipe_result
        self._rule_result = rule_result
        self.save_button.setEnabled(True)
        suffix = "" if rule_result is None else f" / {rule_result.status.value}"
        self.status_label.setText(
            f"Ready: {recipe_result.recipe_name} / {recipe_result.state.value}{suffix}"
        )

    def clear_result(self) -> None:
        self._recipe_result = None
        self._rule_result = None
        self.save_button.setEnabled(False)
        self.status_label.setText("Run a recipe to enable evidence capture.")

    def set_recipe_running(self, running: bool) -> None:
        if running:
            self.save_button.setEnabled(False)
        elif self._recipe_result is not None and self._cancel_event is None:
            self.save_button.setEnabled(True)

    def _set_busy(self, busy: bool) -> None:
        self.save_button.setEnabled(not busy and self._recipe_result is not None)
        self.cancel_button.setEnabled(busy)
        self.screen_checkbox.setEnabled(not busy)
        self.waveform_checkbox.setEnabled(not busy)
        self.points_combo.setEnabled(not busy)

    def _save_clicked(self) -> None:
        recipe_result = self._recipe_result
        if recipe_result is None:
            return
        filename, _filter = QFileDialog.getSaveFileName(
            self,
            "Save A18 evidence bundle",
            f"{_safe_filename(recipe_result.recipe_name)}.dpoe",
            "DPO4000 Evidence (*.dpoe);;All files (*)",
        )
        if not filename:
            return

        output = Path(filename)
        rule_result = self._rule_result
        include_screen = self.screen_checkbox.isChecked()
        include_waveforms = self.waveform_checkbox.isChecked()
        point_count = self.points_combo.currentData()
        cancel_event = threading.Event()
        self._cancel_event = cancel_event
        self._set_busy(True)
        self.status_label.setText("Capturing and writing evidence…")

        def execute(scope: Any) -> EvidenceBundleResult:
            identity = scope.query_identity()
            if cancel_event.is_set():
                raise RuntimeError("Evidence capture cancelled")
            screen = scope.read_screen_png() if include_screen else None
            if cancel_event.is_set():
                raise RuntimeError("Evidence capture cancelled")
            waveforms = (
                scope.read_enabled_waveforms(point_count=point_count)
                if include_waveforms
                else None
            )
            if cancel_event.is_set():
                raise RuntimeError("Evidence capture cancelled")
            return create_evidence_bundle(
                output,
                recipe_result=recipe_result,
                rule_result=rule_result,
                screen_png=screen,
                waveforms=waveforms,
                scope_identity=identity,
                metadata={"producer": "DPO4000 Desk", "feature": "A18"},
                cancel=cancel_event,
            )

        self._run_action(
            "Create A18 evidence bundle",
            execute,
            on_success=self._evidence_finished,
            on_error=self._evidence_error,
            retain_session=True,
        )

    def _evidence_finished(self, result: Any) -> None:
        self._cancel_event = None
        self._set_busy(False)
        if not isinstance(result, EvidenceBundleResult):
            self.status_label.setText("Evidence worker returned an invalid result.")
            return
        mib = result.size_bytes / (1024 * 1024)
        self.status_label.setText(
            f"Saved {result.path} — {result.artifact_count} artifacts, "
            f"{mib:.2f} MiB, {result.metrics.total_s:.3f}s, "
            f"SHA-256 {result.sha256[:12]}…"
        )

    def _evidence_error(self, exc: Exception) -> None:
        self._cancel_event = None
        self._set_busy(False)
        self.status_label.setText(f"Evidence failed: {exc}")

    def _cancel_clicked(self) -> None:
        if self._cancel_event is None:
            return
        self._cancel_event.set()
        self.cancel_button.setEnabled(False)
        self.status_label.setText(
            "Cancelling evidence… an active VISA transfer is bounded by its driver timeout."
        )


__all__ = ["EvidenceBundlePanel"]
