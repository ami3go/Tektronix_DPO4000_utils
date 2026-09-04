"""Logger L2 MATH waveform source integration."""

from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QFormLayout

from .logger_window import QtScopeWindow as LoggerL1QtScopeWindow


class QtScopeWindow(LoggerL1QtScopeWindow):
    """L1 Logger extended with the scope MATH waveform as a selectable source."""

    def _build_logger_sources_card(self):
        card = super()._build_logger_sources_card()
        form = card.layout()
        self.logger_math_check = QCheckBox("MATH")
        self.logger_math_check.setChecked(False)
        if isinstance(form, QFormLayout):
            form.addRow("Math", self.logger_math_check)
        return card

    def _logger_selected_sources(self) -> tuple[str, ...]:
        sources = list(super()._logger_selected_sources())
        check = getattr(self, "logger_math_check", None)
        if check is not None and check.isChecked():
            sources.append("MATH")
        return tuple(sources)

    def _logger_refresh_status(self) -> None:
        super()._logger_refresh_status()
        check = getattr(self, "logger_math_check", None)
        if check is not None:
            check.setEnabled(not self._logger_active() and not bool(getattr(self, "_operation_active", False)))


__all__ = ["QtScopeWindow"]
