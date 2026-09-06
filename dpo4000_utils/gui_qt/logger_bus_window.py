"""Logger L6 decoded BUS event mode with explicit capability gating."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QFormLayout, QHBoxLayout, QLabel, QWidget

from ..logger.models import LoggerConfig, LoggerMode
from ..logger.output import LoggerOutputSession
from .logger_measurement_window import QtScopeWindow as LoggerL5QtScopeWindow
from .logger_page_layout import FILE_PAGE_INDEX


class QtScopeWindow(LoggerL5QtScopeWindow):
    """L5 Logger extended with normalized BUS1..BUS4 decoded event output."""

    def _build_logger_sources_card(self):
        card = super()._build_logger_sources_card()
        form = card.layout()
        if self.logger_mode_combo.findText(LoggerMode.BUS.value) < 0:
            self.logger_mode_combo.addItem(LoggerMode.BUS.value)
        self.logger_bus_checks: dict[int, QCheckBox] = {}
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        for bus in range(1, 5):
            check = QCheckBox(f"BUS{bus}")
            check.setChecked(bus == 1)
            self.logger_bus_checks[bus] = check
            row_layout.addWidget(check)
        self.logger_bus_row = row
        note = QLabel(
            "Decoded event logging is enabled only when the connected driver reports a hardware-qualified transaction extraction capability."
        )
        note.setObjectName("MutedLabel")
        note.setWordWrap(True)
        if isinstance(form, QFormLayout):
            form.addRow("Decoded buses", row)
            form.addRow(note)
        self._logger_mode_changed()
        return card

    def _logger_mode_changed(self, *_args) -> None:
        super()._logger_mode_changed(*_args)
        row = getattr(self, "logger_bus_row", None)
        if row is not None:
            row.setVisible(self._logger_mode() is LoggerMode.BUS)

    def _logger_selected_buses(self) -> tuple[int, ...]:
        return tuple(bus for bus, check in self.logger_bus_checks.items() if check.isChecked())

    def _logger_config(self) -> LoggerConfig:
        mode = self._logger_mode()
        if mode is LoggerMode.BUS:
            return LoggerConfig(
                mode=mode,
                interval_s=float(self.logger_interval.value()),
                waveform_sources=(),
                bus_slots=self._logger_selected_buses(),
            )
        return super()._logger_config()

    def _open_logger_output(self, config: LoggerConfig) -> LoggerOutputSession:
        self._ensure_control_page_built(FILE_PAGE_INDEX)
        root = Path(self.output_folder.text()).expanduser() / "logger"
        return LoggerOutputSession(
            root,
            self._selected_output_format(),
            mode=config.mode,
            measurement_slots=config.measurement_slots,
            run_metadata={
                "mode": config.mode.value,
                "waveform_sources": list(config.waveform_sources),
                "measurement_slots": list(config.measurement_slots),
                "bus_slots": list(config.bus_slots),
                "encoding": config.encoding,
                "sample_width": config.sample_width,
            },
        )

    def _continue_bus_logger_start(self) -> None:
        """Continue below L6 after asynchronous BUS capability qualification."""
        previous_starting = getattr(self, "_logger_starting", False)
        if hasattr(self, "_logger_starting"):
            self._logger_starting = True
        try:
            super(QtScopeWindow, self).start_logger()
        finally:
            if hasattr(self, "_logger_starting"):
                self._logger_starting = previous_starting
        self._logger_refresh_status()

    def start_logger(self) -> None:
        if self._logger_mode() is LoggerMode.BUS:
            if not bool(getattr(self, "_connection_ok", False)):
                self._message(
                    "Logger",
                    "Test the scope connection before starting BUS Logger.",
                    error=True,
                )
                return

            def capability_checked(result: object) -> None:
                if result is True:
                    self._continue_bus_logger_start()
                    return
                self._message(
                    "Logger BUS",
                    "Decoded BUS transaction extraction is not hardware-qualified for this "
                    "driver/scope. BUS configuration remains available, but Logger will not "
                    "invent an undocumented extraction command.",
                    error=True,
                )
                self._logger_refresh_status()

            self._run_action(
                "Checking decoded BUS logger capability",
                lambda scope: bool(scope.supports_decoded_bus_events()),
                on_success=capability_checked,
                on_error=lambda exc: self._message(
                    "Logger BUS",
                    f"Could not verify decoded BUS capability: {exc}",
                    error=True,
                ),
                retain_session=True,
            )
            return
        super().start_logger()

    def _logger_refresh_status(self) -> None:
        super()._logger_refresh_status()
        editable = not self._logger_active() and not bool(getattr(self, "_operation_active", False))
        for check in getattr(self, "logger_bus_checks", {}).values():
            check.setEnabled(editable)


__all__ = ["QtScopeWindow"]
