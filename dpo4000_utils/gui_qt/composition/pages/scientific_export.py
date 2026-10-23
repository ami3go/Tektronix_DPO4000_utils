"""A21 scientific export controls attached to the existing File page."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ....scientific_export import (
    ScientificExportResult,
    ScientificFormat,
    export_scientific_dataset,
)


class ScientificExportPanel(QGroupBox):
    """Capture enabled channels and export them without blocking the GUI thread."""

    def __init__(
        self,
        *,
        run_action: Callable[..., Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Scientific Export (A21)", parent)
        self.setObjectName("scientificExportPanel")
        self._run_action = run_action
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        hint = QLabel(
            "Export enabled-channel waveforms to NumPy NPZ or a portable DPOZ "
            "archive. Acquisition and file writing run on the serialized worker."
        )
        hint.setWordWrap(True)
        hint.setObjectName("MutedLabel")
        layout.addWidget(hint)

        form = QFormLayout()
        self.format_combo = QComboBox()
        self.format_combo.setObjectName("scientificExportFormat")
        self.format_combo.addItem("NumPy NPZ", ScientificFormat.NPZ.value)
        self.format_combo.addItem("Portable DPOZ (ZIP + CSV + raw)", ScientificFormat.DPOZ.value)
        form.addRow("Format", self.format_combo)

        self.points_combo = QComboBox()
        self.points_combo.setObjectName("scientificExportPoints")
        self.points_combo.addItem("Full record", None)
        for count in (1_000, 10_000, 100_000, 1_000_000):
            self.points_combo.addItem(f"{count:,} points", count)
        form.addRow("Record size", self.points_combo)

        self.compressed_checkbox = QCheckBox("Compress archive")
        self.compressed_checkbox.setObjectName("scientificExportCompressed")
        self.compressed_checkbox.setChecked(False)
        form.addRow("Storage", self.compressed_checkbox)
        layout.addLayout(form)

        actions = QHBoxLayout()
        self.export_button = QPushButton("Export Enabled Channels…")
        self.export_button.setObjectName("scientificExportButton")
        self.export_button.clicked.connect(self._export_clicked)
        actions.addWidget(self.export_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("scientificExportStatus")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

    def _selected_format(self) -> ScientificFormat:
        return ScientificFormat(str(self.format_combo.currentData()))

    def _export_clicked(self) -> None:
        export_format = self._selected_format()
        if export_format is ScientificFormat.NPZ:
            suffix = ".npz"
            file_filter = "NumPy archive (*.npz)"
        else:
            suffix = ".dpoz"
            file_filter = "DPO scientific archive (*.dpoz)"
        filename, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export scientific waveform data",
            f"dpo4000_waveforms{suffix}",
            f"{file_filter};;All files (*)",
        )
        if not filename:
            return
        path = Path(filename)
        if path.suffix.lower() not in {".npz", ".dpoz", ".zip"}:
            path = path.with_suffix(suffix)

        point_count = self.points_combo.currentData()
        compressed = self.compressed_checkbox.isChecked()
        self.export_button.setEnabled(False)
        self.status_label.setText("Capturing and exporting…")

        def execute(scope: Any) -> ScientificExportResult:
            waveforms = scope.read_enabled_waveforms(point_count=point_count)
            return export_scientific_dataset(
                path,
                waveforms,
                format=export_format,
                metadata={
                    "producer": "DPO4000 Desk",
                    "scope_identity": scope.query_identity(),
                },
                compressed=compressed,
            )

        self._run_action(
            "A21 scientific export",
            execute,
            on_success=self._export_finished,
            on_error=self._export_error,
            retain_session=True,
        )

    def _export_finished(self, result: Any) -> None:
        self.export_button.setEnabled(True)
        if not isinstance(result, ScientificExportResult):
            self.status_label.setText("Scientific export returned an invalid result")
            return
        self.status_label.setText(
            f"Exported {result.trace_count} traces / {result.sample_count:,} samples to "
            f"{result.path} — {result.bytes_written / 1_000_000:.3f} MB in "
            f"{result.duration_s:.3f}s, {result.samples_per_second:,.0f} samples/s, "
            f"{result.megabytes_per_second:.2f} MB/s"
        )

    def _export_error(self, exc: Exception) -> None:
        self.export_button.setEnabled(True)
        self.status_label.setText(f"Scientific export failed: {exc}")


def attach_scientific_export_panel(host: Any, page: QWidget) -> QWidget:
    """Attach A21 controls to the mature File page without replacing its features."""
    layout = page.layout()
    if layout is None:
        layout = QVBoxLayout(page)
    panel = ScientificExportPanel(run_action=host._run_action, parent=page)
    layout.addWidget(panel)
    return page


__all__ = ["ScientificExportPanel", "attach_scientific_export_panel"]
