"""A15/A16 recipe and pass/fail page for composition-first DPO4000 Desk."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import Qt, Signal
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

from ....recipe import (
    Recipe,
    RecipeResult,
    RecipeRunState,
    RecipeSequencer,
    StepResult,
    recipe_from_mapping,
    recipe_to_mapping,
)
from ....rules import (
    RuleEngine,
    RuleSet,
    RuleSetResult,
    recipe_result_values,
    rule_set_from_mapping,
    rule_set_to_mapping,
)


class RecipePage(QWidget):
    """Edit/run A15 recipes and evaluate A16 rules over completed step values."""

    step_started = Signal(int, str)
    step_finished = Signal(object)

    def __init__(
        self,
        *,
        run_action: Callable[..., Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("A16RecipeRulePage")
        self._run_action = run_action
        self._sequencer: RecipeSequencer | None = None
        self._active_recipe: Recipe | None = None
        self._active_rule_set: RuleSet | None = None
        self._build_ui()
        self.step_started.connect(self._on_step_started)
        self.step_finished.connect(self._on_step_finished)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(10)

        title = QLabel("Test Recipe / Sequencer + Pass/Fail Rules")
        title.setObjectName("recipeTitle")
        layout.addWidget(title)

        hint = QLabel(
            "Recipes execute validated public DPO4000 driver methods in the existing "
            "serialized worker. A16 rules evaluate completed numeric step values locally. "
            "Raw SCPI, private attributes, session management, Python expressions, and "
            "shell commands are rejected."
        )
        hint.setWordWrap(True)
        hint.setObjectName("MutedLabel")
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        self.load_button = QPushButton("Load Recipe")
        self.load_button.setObjectName("recipeLoadButton")
        self.save_button = QPushButton("Save Recipe")
        self.save_button.setObjectName("recipeSaveButton")
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
            self.save_button,
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
                    "name": "Read trigger state",
                    "steps": [
                        {
                            "kind": "call",
                            "name": "Read A trigger",
                            "method": "get_trigger_configuration",
                        },
                        {
                            "kind": "delay",
                            "name": "Settle",
                            "seconds": 0.1,
                        },
                        {
                            "kind": "call",
                            "name": "Read holdoff",
                            "method": "get_trigger_holdoff",
                        },
                    ],
                },
                indent=2,
            )
        )
        layout.addWidget(self.editor, 2)

        rules_header = QHBoxLayout()
        rules_title = QLabel("A16 Pass/Fail Rules")
        rules_title.setObjectName("ruleSetTitle")
        rules_header.addWidget(rules_title)
        rules_header.addStretch(1)
        self.rules_load_button = QPushButton("Load Rules")
        self.rules_load_button.setObjectName("ruleSetLoadButton")
        self.rules_save_button = QPushButton("Save Rules")
        self.rules_save_button.setObjectName("ruleSetSaveButton")
        self.rules_validate_button = QPushButton("Validate Rules")
        self.rules_validate_button.setObjectName("ruleSetValidateButton")
        rules_header.addWidget(self.rules_load_button)
        rules_header.addWidget(self.rules_save_button)
        rules_header.addWidget(self.rules_validate_button)
        layout.addLayout(rules_header)

        self.rules_editor = QPlainTextEdit()
        self.rules_editor.setObjectName("ruleSetJsonEditor")
        self.rules_editor.setPlainText(
            json.dumps(
                {
                    "version": 1,
                    "name": "Holdoff sanity",
                    "root": {
                        "type": "compare",
                        "id": "holdoff_non_negative",
                        "input": "Read holdoff",
                        "operator": ">=",
                        "value": 0.0,
                    },
                },
                indent=2,
            )
        )
        layout.addWidget(self.rules_editor, 1)

        self.status_label = QLabel("Idle")
        self.status_label.setObjectName("recipeStatusLabel")
        layout.addWidget(self.status_label)

        self.results = QTableWidget(0, 5)
        self.results.setObjectName("recipeResultsTable")
        self.results.setHorizontalHeaderLabels(
            ["#", "Step", "Status", "Attempts", "Duration (s)"]
        )
        self.results.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.results, 1)

        self.rule_results = QTableWidget(0, 5)
        self.rule_results.setObjectName("ruleSetResultsTable")
        self.rule_results.setHorizontalHeaderLabels(
            ["Rule", "Status", "Actual", "Expected", "Reason"]
        )
        self.rule_results.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.rule_results, 1)

        self.load_button.clicked.connect(self._load_json)
        self.save_button.clicked.connect(self._save_json)
        self.validate_button.clicked.connect(self._validate_clicked)
        self.run_button.clicked.connect(self._run_clicked)
        self.pause_button.clicked.connect(self._pause_clicked)
        self.resume_button.clicked.connect(self._resume_clicked)
        self.cancel_button.clicked.connect(self._cancel_clicked)
        self.rules_load_button.clicked.connect(self._load_rules_json)
        self.rules_save_button.clicked.connect(self._save_rules_json)
        self.rules_validate_button.clicked.connect(self._validate_rules_clicked)
        self._set_running(False)

    def _set_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running)
        self.load_button.setEnabled(not running)
        self.save_button.setEnabled(not running)
        self.validate_button.setEnabled(not running)
        self.rules_load_button.setEnabled(not running)
        self.rules_save_button.setEnabled(not running)
        self.rules_validate_button.setEnabled(not running)
        self.editor.setReadOnly(running)
        self.rules_editor.setReadOnly(running)
        # Control buttons are enabled when the first worker-side step starts, which
        # avoids a race before the sequencer object exists.
        self.pause_button.setEnabled(False)
        self.resume_button.setEnabled(False)
        self.cancel_button.setEnabled(False)

    def _parse_recipe(self) -> Recipe:
        try:
            document = json.loads(self.editor.toPlainText())
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid recipe JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}"
            ) from exc
        return recipe_from_mapping(document)

    def _parse_rules(self) -> RuleSet | None:
        text = self.rules_editor.toPlainText().strip()
        if not text:
            return None
        try:
            document = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid rules JSON: {exc.msg} at line {exc.lineno}, column {exc.colno}"
            ) from exc
        return rule_set_from_mapping(document)

    def _validate_clicked(self) -> None:
        try:
            recipe = self._parse_recipe()
            rules = self._parse_rules()
        except Exception as exc:
            self.status_label.setText(f"Invalid: {exc}")
            return
        suffix = "no rules" if rules is None else f"rules: {rules.name}"
        self.status_label.setText(
            f"Valid: {recipe.name} ({len(recipe.steps)} steps), {suffix}"
        )

    def _validate_rules_clicked(self) -> None:
        try:
            rules = self._parse_rules()
        except Exception as exc:
            self.status_label.setText(f"Invalid rules: {exc}")
            return
        if rules is None:
            self.status_label.setText("Rules disabled: editor is empty")
        else:
            self.status_label.setText(f"Valid rules: {rules.name}")

    def _load_json(self) -> None:
        filename, _filter = QFileDialog.getOpenFileName(
            self,
            "Load recipe",
            "",
            "JSON (*.json);;All files (*)",
        )
        if not filename:
            return
        try:
            self.editor.setPlainText(Path(filename).read_text(encoding="utf-8"))
            self._validate_clicked()
        except OSError as exc:
            QMessageBox.warning(self, "Load recipe", str(exc))

    def _save_json(self) -> None:
        try:
            recipe = self._parse_recipe()
        except Exception as exc:
            self.status_label.setText(f"Invalid: {exc}")
            return
        filename, _filter = QFileDialog.getSaveFileName(
            self,
            "Save recipe",
            f"{recipe.name.replace(' ', '_')}.json",
            "JSON (*.json);;All files (*)",
        )
        if not filename:
            return
        path = Path(filename)
        try:
            path.write_text(
                json.dumps(recipe_to_mapping(recipe), indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            QMessageBox.warning(self, "Save recipe", str(exc))
            return
        self.status_label.setText(f"Saved: {path}")

    def _load_rules_json(self) -> None:
        filename, _filter = QFileDialog.getOpenFileName(
            self,
            "Load pass/fail rules",
            "",
            "JSON (*.json);;All files (*)",
        )
        if not filename:
            return
        try:
            self.rules_editor.setPlainText(Path(filename).read_text(encoding="utf-8"))
            self._validate_rules_clicked()
        except OSError as exc:
            QMessageBox.warning(self, "Load pass/fail rules", str(exc))

    def _save_rules_json(self) -> None:
        try:
            rules = self._parse_rules()
        except Exception as exc:
            self.status_label.setText(f"Invalid rules: {exc}")
            return
        if rules is None:
            self.status_label.setText("Nothing to save: rules editor is empty")
            return
        filename, _filter = QFileDialog.getSaveFileName(
            self,
            "Save pass/fail rules",
            f"{rules.name.replace(' ', '_')}_rules.json",
            "JSON (*.json);;All files (*)",
        )
        if not filename:
            return
        path = Path(filename)
        try:
            path.write_text(
                json.dumps(rule_set_to_mapping(rules), indent=2) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            QMessageBox.warning(self, "Save pass/fail rules", str(exc))
            return
        self.status_label.setText(f"Saved rules: {path}")

    def _prepare_result_rows(self, recipe: Recipe) -> None:
        self.results.setRowCount(len(recipe.steps))
        for row, step in enumerate(recipe.steps):
            values = (row + 1, step.name, "Pending", "", "")
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column in (0, 3, 4):
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight
                        | Qt.AlignmentFlag.AlignVCenter
                    )
                self.results.setItem(row, column, item)
        self.rule_results.setRowCount(0)

    def _run_clicked(self) -> None:
        try:
            recipe = self._parse_recipe()
            rules = self._parse_rules()
        except Exception as exc:
            self.status_label.setText(f"Invalid: {exc}")
            return

        self._active_recipe = recipe
        self._active_rule_set = rules
        self._prepare_result_rows(recipe)
        self._set_running(True)
        self.status_label.setText(f"Starting: {recipe.name}")

        def execute(scope: Any) -> RecipeResult:
            self._sequencer = RecipeSequencer(scope)
            return self._sequencer.run(
                recipe,
                on_step_start=lambda index, step: self.step_started.emit(
                    index,
                    step.name,
                ),
                on_step_finish=lambda result: self.step_finished.emit(result),
            )

        self._run_action(
            "Run A15 recipe",
            execute,
            on_success=self._run_finished,
            on_error=self._run_error,
            retain_session=True,
        )

    def _on_step_started(self, index: int, name: str) -> None:
        if 0 <= index < self.results.rowCount():
            self.results.item(index, 2).setText("Running")
        self.pause_button.setEnabled(True)
        self.resume_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.status_label.setText(f"Running step {index + 1}: {name}")

    def _on_step_finished(self, result: object) -> None:
        if not isinstance(result, StepResult):
            return
        row = result.index
        if 0 <= row < self.results.rowCount():
            self.results.item(row, 2).setText("Done")
            self.results.item(row, 3).setText(str(result.attempts))
            self.results.item(row, 4).setText(f"{result.duration_s:.6f}")

    def _show_rule_result(self, result: RuleSetResult) -> None:
        evaluations = result.evaluations
        self.rule_results.setRowCount(len(evaluations))
        for row, evaluation in enumerate(evaluations):
            actual = "" if evaluation.actual is None else f"{evaluation.actual:.12g}"
            expected = json.dumps(dict(evaluation.expected), sort_keys=True)
            values = (
                evaluation.rule_id,
                evaluation.status.value,
                actual,
                expected,
                evaluation.reason,
            )
            for column, value in enumerate(values):
                self.rule_results.setItem(row, column, QTableWidgetItem(str(value)))

    def _clear_active(self) -> None:
        self._sequencer = None
        self._active_recipe = None
        self._active_rule_set = None

    def _run_finished(self, result: Any) -> None:
        self._set_running(False)
        rules = self._active_rule_set
        if not isinstance(result, RecipeResult):
            self._clear_active()
            self.status_label.setText("Recipe finished without a valid result")
            return

        if result.state is RecipeRunState.FAILED:
            for row in range(self.results.rowCount()):
                if self.results.item(row, 2).text() == "Running":
                    self.results.item(row, 2).setText("Failed")
                    break
            self._clear_active()
            self.status_label.setText(f"Failed: {result.error or 'unknown error'}")
            return
        if result.state is RecipeRunState.CANCELLED:
            for row in range(self.results.rowCount()):
                if self.results.item(row, 2).text() == "Running":
                    self.results.item(row, 2).setText("Cancelled")
                    break
            self._clear_active()
            self.status_label.setText(
                f"Cancelled: {result.recipe_name} after {result.duration_s:.3f}s"
            )
            return

        if rules is None:
            self._clear_active()
            self.status_label.setText(
                f"Completed: {result.recipe_name} — {len(result.steps)} steps, "
                f"{result.duration_s:.3f}s"
            )
            return

        try:
            rule_result = RuleEngine().evaluate(rules, recipe_result_values(result))
        except Exception as exc:
            self._clear_active()
            self.status_label.setText(f"Recipe completed; rule evaluation invalid: {exc}")
            return
        self._show_rule_result(rule_result)
        self._clear_active()
        self.status_label.setText(
            f"Completed: {result.recipe_name} — {len(result.steps)} steps, "
            f"{result.duration_s:.3f}s — {rule_result.status.value}"
        )

    def _run_error(self, exc: Exception) -> None:
        self._set_running(False)
        self._clear_active()
        self.status_label.setText(f"Worker failure: {exc}")

    def _pause_clicked(self) -> None:
        if self._sequencer is None:
            return
        self._sequencer.pause()
        self.pause_button.setEnabled(False)
        self.resume_button.setEnabled(True)
        self.status_label.setText("Paused")

    def _resume_clicked(self) -> None:
        if self._sequencer is None:
            return
        self._sequencer.resume()
        self.pause_button.setEnabled(True)
        self.resume_button.setEnabled(False)
        self.status_label.setText("Running")

    def _cancel_clicked(self) -> None:
        if self._sequencer is None:
            return
        self._sequencer.cancel()
        self.pause_button.setEnabled(False)
        self.resume_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.status_label.setText("Cancelling…")


def build_recipe_page(host: Any) -> QWidget:
    """Build the production A15/A16 Recipe page at the composition boundary."""
    return RecipePage(run_action=host._run_action, parent=host)


__all__ = ["RecipePage", "build_recipe_page"]
