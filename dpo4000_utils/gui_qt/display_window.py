"""Stable PySide6 window with DPO4000 display controls.

Adds practical front-panel display settings to the launched Qt GUI without
changing the existing top-menu page structure.  The controls live in the
Settings page because they are scope-display settings rather than acquisition or
trigger setup.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QWidget,
)

from .stable_window import QtScopeWindow as StableQtScopeWindow

DISPLAY_PERSISTENCE_VALUES = (
    "AUTO",
    "MINIMUM",
    "INFINITE",
    "CLEAR",
    "0.5",
    "1",
    "2",
    "5",
    "10",
)
DISPLAY_SETUP_QUERIES = {
    "backlight": "DISPLAY:INTENSITY:BACKLIGHT?",
    "waveform": "DISPLAY:INTENSITY:WAVEFORM?",
    "graticule": "DISPLAY:INTENSITY:GRATICULE?",
    "persistence": "DISPLAY:PERSISTENCE?",
    "message_text": "MESSAGE:SHOW?",
    "message_state": "MESSAGE:STATE?",
}
DISPLAY_SCOPE_ACTIONS = {
    "read_display_settings",
    "apply_display_settings",
    "clear_display_message",
}


class QtScopeWindow(StableQtScopeWindow):
    """Stable launched Qt window with display contrast, persistence, and message controls."""

    def _callback_requires_scope(self, callback) -> bool:
        """Make display-setting buttons follow the same IDN-first safety gate."""
        if getattr(callback, "__name__", "") in DISPLAY_SCOPE_ACTIONS:
            return True
        return super()._callback_requires_scope(callback)

    def _build_settings_tab(self) -> QWidget:
        """Add a display-settings card to the existing Settings page."""
        page = super()._build_settings_tab()
        layout = page.layout()
        if layout is not None:
            insert_at = max(0, layout.count() - 1)
            layout.insertWidget(insert_at, self._build_display_settings_card())
        return page

    def _build_display_settings_card(self) -> QGroupBox:
        card = self._card("Display, persistence, and screen text")
        form = QFormLayout(card)
        self._prepare_form(form)

        self.display_backlight = QLineEdit("100")
        self.display_backlight.setToolTip("DISPLAY:INTENSITY:BACKLIGHT, usually 0..100.")
        self.display_waveform_intensity = QLineEdit("")
        self.display_waveform_intensity.setToolTip("Optional DISPLAY:INTENSITY:WAVEFORM value.")
        self.display_graticule_intensity = QLineEdit("")
        self.display_graticule_intensity.setToolTip("Optional DISPLAY:INTENSITY:GRATICULE value.")

        self.display_persistence = QComboBox()
        self.display_persistence.setEditable(True)
        self.display_persistence.addItems(DISPLAY_PERSISTENCE_VALUES)
        self.display_persistence.setToolTip(
            "DISPLAY:PERSISTENCE accepts AUTO, MINIMUM, INFINITE, CLEAR, or a time value."
        )

        self.display_message_text = QLineEdit("")
        self.display_message_text.setMaxLength(120)
        self.display_message_text.setToolTip("MESSAGE:SHOW text added as a message box on the scope screen.")
        self.display_message_state = QCheckBox("Show text box on scope screen")

        form.addRow("Contrast / backlight %", self.display_backlight)
        form.addRow("Waveform intensity", self.display_waveform_intensity)
        form.addRow("Graticule intensity", self.display_graticule_intensity)
        form.addRow("Persistence", self.display_persistence)
        form.addRow("Screen text", self.display_message_text)
        form.addRow(self.display_message_state)

        hint = QLabel(
            "Backlight/waveform/graticule values map to DISPLAY:INTENSITY commands. "
            "Persistence maps to DISPLAY:PERSISTENCE. Screen text uses MESSAGE:SHOW, "
            "MESSAGE:STATE, and MESSAGE:CLEAR. Some firmware may reject unsupported values."
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        form.addRow(hint)

        buttons = QHBoxLayout()
        read_button = self._button("Read display", self.read_display_settings)
        apply_button = self._accent_button("Apply display", self.apply_display_settings)
        clear_button = self._button("Clear text", self.clear_display_message)
        for button in (read_button, apply_button, clear_button):
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            buttons.addWidget(button)
        form.addRow(buttons)
        return self._prepare_drawer_card(card)

    @staticmethod
    def _quote_scpi_string(value: str) -> str:
        """Quote screen message text for SCPI while keeping it single-line and safe."""
        clean = " ".join(str(value).replace('"', "'").splitlines()).strip()
        return f'"{clean}"'

    def read_display_settings(self) -> None:
        def action(scope) -> dict[str, str]:
            instrument = getattr(scope, "scope", None)
            if instrument is None:
                raise ConnectionError("Oscilloscope is not connected.")
            return {
                name: self._query_optional(instrument, query)
                for name, query in DISPLAY_SETUP_QUERIES.items()
            }

        result = self._run_action("Reading display settings", action)
        if isinstance(result, dict):
            self.display_backlight.setText(result.get("backlight", ""))
            self.display_waveform_intensity.setText(result.get("waveform", ""))
            self.display_graticule_intensity.setText(result.get("graticule", ""))
            self._set_combo_text(self.display_persistence, result.get("persistence", ""))
            self.display_message_text.setText(result.get("message_text", ""))
            self.display_message_state.setChecked(
                self._bool_from_scope_response(result.get("message_state", "0"))
            )

    def apply_display_settings(self) -> None:
        backlight = self.display_backlight.text()
        waveform = self.display_waveform_intensity.text()
        graticule = self.display_graticule_intensity.text()
        persistence = self.display_persistence.currentText().strip().upper()
        message_text = self.display_message_text.text().strip()
        message_state = self.display_message_state.isChecked()

        def action(scope) -> str:
            instrument = getattr(scope, "scope", None)
            if instrument is None:
                raise ConnectionError("Oscilloscope is not connected.")
            self._write_if_text(instrument, "DISPLAY:INTENSITY:BACKLIGHT", backlight)
            self._write_if_text(instrument, "DISPLAY:INTENSITY:WAVEFORM", waveform)
            self._write_if_text(instrument, "DISPLAY:INTENSITY:GRATICULE", graticule)
            self._write_if_text(instrument, "DISPLAY:PERSISTENCE", persistence)
            if message_text:
                instrument.write(f"MESSAGE:SHOW {self._quote_scpi_string(message_text)}")
            instrument.write(f"MESSAGE:STATE {'ON' if message_state else 'OFF'}")
            return "Display settings applied"

        self._run_action("Applying display settings", action)

    def clear_display_message(self) -> None:
        def action(scope) -> str:
            instrument = getattr(scope, "scope", None)
            if instrument is None:
                raise ConnectionError("Oscilloscope is not connected.")
            instrument.write("MESSAGE:CLEAR")
            instrument.write("MESSAGE:STATE OFF")
            return "Screen text cleared"

        result = self._run_action("Clearing display screen text", action)
        if result is not None:
            self.display_message_text.clear()
            self.display_message_state.setChecked(False)


__all__ = [
    "DISPLAY_PERSISTENCE_VALUES",
    "DISPLAY_SCOPE_ACTIONS",
    "DISPLAY_SETUP_QUERIES",
    "QtScopeWindow",
]
