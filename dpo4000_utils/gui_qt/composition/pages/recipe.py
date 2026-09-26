"""A15 recipe/sequencer page for the composition-first DPO4000 Desk UI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ....recipe import Recipe, RecipeRunState, RecipeSequencer, recipe_from_mapping


class RecipePage(QWidget):
    """Edit and execute a versioned A15 JSON recipe via the worker action boundary."""

    def __init__(
        self,
        *,
        run_action: Callable[..., Any],
        scope_provider: Callable[[], Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._run_action = run_action
        self._scope_provider = scope_provider
        self._sequencer: RecipeSequencer | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        title = QLabel("Test Recipe / Sequencer")
        title.setObjectName("recipeTitle")
        layout.addWidget(title)

        hint = QLabel(
            "Recipes execute validated public driver methods in order. "
            "Raw SCPI and private driver access are not accepted."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        self.load_button = QPushButton("Load JSON")
        self.load_button.setObjectName("recipeLoadButton")
        self.validate_button = QPushButton("Validate")
        self.validate_button.setObjectName("recipeValidateButton")
        self.run_button = QPushButton("Run")
        self.run_button.setObjectName("recipeRunButton")
        self.pause_button = QPushButton("Pause")
        self.pause_button.setObjectName("recipePauseButton")
        self.resume_button = QPushButton("Resume")
        self.resume_button.setObjectName("recipeResumeButton")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("recipeCancelButton")
        for button in (
            self.load_button,
            self.validate_button,
            self.run_button,
            self.pause_button,
            self.resume_button,
            self.cancel_button,
        ):
            buttons.addWidget(button)
        layout.addLayout(buttons)

        self.editor = QPlainTextEdit()
        self.editor.setObjectName("recipeJsonEditor")
        self.editor.setPlainText(
            json.dumps(
                {
                    "version": 1,
                    "name": "New recipe",
                    "steps": [{"kind": "delay", "name": "Settle", "seconds": 0.1}],
                },
                indent=2,
            )
        )
        layout.addWidget(self.editor, 2)

        self.status_label = QLabel("Idle")
        self.status_label.setObjectName("recipeStatusLabel")
        layout.addWidget(self.status_label)

        self.results = QTableWidget(0, 4)
        self.results.setObjectName("recipeResultsTable")
        self.results.setHorizontalHeaderLabels(["#", "Step", "Attempts", "Duration (s)"])
        self.results.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.results, 1)

        self.load_button.clicked.connect(self._load_json)
        self.validate_button.clicked.connect(self._validate_clicked)
        self.run_button.clicked.connect(self._run_clicked)
        self.pause_button.clicked.connect(self._pause_clicked)
        self.resume_button.clicked.connect(self._resume_clicked)
        self.cancel_button.clicked.connect(self._cancel_clicked)
        self._set_running(False)

    def _set_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running)
        self.load_button.setEnabled(not running)
        self.validate_button.setEnabled(not running)
        self.pause_button.setEnabled(running)
        self.resume_button.setEnabled(running)
        self.cancel_button.setEnabled(running)

    def _parse_recipe(self) -> Recipe:
        try:
            document = json.loads(self.editor.toPlainText())
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}") from exc
        return recipe_from_mapping(document)

    def _validate_clicked(self) -> None:
        try:
            recipe = self._parse_recipe()
        except Exception as exc:
            self.status_label.setText(f"Invalid: {exc}")
            return
        self.status_label.setText(f"Valid: {recipe.name} ({len(recipe.steps)} steps)")

    def _load_json(self) -> None:
        filename, _filter = QFileDialog.getOpenFileName(self, "Load recipe", "", "JSON (*.json);;All files (*)")
        if not filename:
            return
        try:
            self.editor.setPlainText(Path(filename).read_text(encoding="utf-8"))
            self._validate_clicked()
        except OSError as exc:
            QMessageBox.warning(self, "Load recipe", str(exc))

    def _run_clicked(self) -> None:
        try:
            recipe = self._parse_recipe()
        except Exception as exc:
            self.status_label.setText(f"Invalid: {exc}")
            return

        self.results.setRowCount(0)
        self._set_running(True)
        self.status_label.setText(f"Running: {recipe.name}")

        def execute() -> Any:
            scope = self._scope_provider()
            self._sequencer = RecipeSequencer(scope)
            return self._sequencer.run(recipe)

        self._run_action(
            "Run recipe",
            execute,
            on_success=self._run_finished,
            on_error=self._run_error,
        )

    def _run_finished(self, result: Any) -> None:
        self._set_running(False)
        self._sequencer = None
        if result is None:
            self.status_label.setText("Recipe finished without a result")
            return
        self.status_label.setText(
            f"{result.state.value}: {result.recipe_name} — {len(result.steps)} steps, {result.duration_s:.3f}s"
        )
        self.results.setRowCount(len(result.steps))
        for row, step in enumerate(result.steps):
            for column, value in enumerate(
                (step.index + 1, step.name, step.attempts, f"{step.duration_s:.6f}")
            ):
                item = QTableWidgetItem(str(value))
                if column in (0, 2, 3):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.results.setItem(row, column, item)
        if result.state is RecipeRunState.FAILED and result.error:
            self.status_label.setText(f"Failed: {result.error}")

    def _run_error(self, exc: Exception) -> None:
        self._set_running(False)
        self._sequencer = None
        self.status_label.setText(f"Failed: {exc}")

    def _pause_clicked(self) -> None:
        if self._sequencer is not None:
            self._sequencer.pause()
            self.status_label.setText("Paused")

    def _resume_clicked(self) -> None:
        if self._sequencer is not None:
            self._sequencer.resume()
            self.status_label.setText("Running")

    def _cancel_clicked(self) -> None:
        if self._sequencer is not None:
            self._sequencer.cancel()
            self.status_label.setText("Cancelling…")
