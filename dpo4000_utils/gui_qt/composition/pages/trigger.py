"""Composition-first Advanced Trigger page for DPO4000 Desk.

The page intentionally talks only to the public driver API.  It exposes the A14
trigger types whose field layouts are hardware-verified (EDGE, PULSE WIDTH/RUNT/
TIMEOUT, LOGIC/SETHOLD, VIDEO), verified holdoff-by-time, and the separate B-trigger
sequence configuration.  BUS and pulse TRANSITION are not offered because their
A14 configuration subtrees are not mapped end-to-end.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ....control import (
    TRIGGER_COUPLINGS,
    TRIGGER_LOGIC_CLOCK_EDGES,
    TRIGGER_LOGIC_FUNCTIONS,
    TRIGGER_LOGIC_INPUT_STATES,
    TRIGGER_LOGIC_PATTERN_WHEN,
    TRIGGER_MODES,
    TRIGGER_PULSE_RUNT_POLARITIES,
    TRIGGER_PULSE_RUNT_WHEN,
    TRIGGER_PULSE_TIMEOUT_POLARITIES,
    TRIGGER_PULSE_WIDTH_POLARITIES,
    TRIGGER_PULSE_WIDTH_WHEN,
    TRIGGER_SEQUENCE_BY,
    TRIGGER_SLOPES,
    TRIGGER_SOURCES,
    TRIGGER_VIDEO_FIELDS,
    TRIGGER_VIDEO_POLARITIES,
    TRIGGER_VIDEO_STANDARDS,
    SequenceTriggerConfig,
    TriggerConfig,
)

_A_TRIGGER_TYPES = ("EDGE", "PULSE", "LOGIC", "VIDEO")
_PULSE_GUI_CLASSES = ("WIDTH", "RUNT", "TIMEOUT")
_LOGIC_GUI_CLASSES = ("LOGIC", "SETHOLD")
_ANALOG_SOURCES = ("CH1", "CH2", "CH3", "CH4")


def _prepare_form(host: Any, form: QFormLayout) -> None:
    prepare = getattr(host, "_prepare_form", None)
    if callable(prepare):
        prepare(form)


def _prepare_card(host: Any, card: QWidget) -> QWidget:
    prepare = getattr(host, "_prepare_drawer_card", None)
    return prepare(card) if callable(prepare) else card


def _combo(items: tuple[str, ...] | list[str], *, editable: bool = False) -> QComboBox:
    widget = QComboBox()
    widget.setEditable(editable)
    widget.addItems(list(items))
    return widget


def _text(widget: QLineEdit) -> str | None:
    value = widget.text().strip()
    return value or None


def _set_combo(combo: QComboBox, value: object) -> None:
    text = str(value or "").strip().upper()
    if not text:
        return
    # Tektronix query readback often abbreviates enum values (RIS, POS, NTS, etc.).
    for index in range(combo.count()):
        candidate = combo.itemText(index).strip().upper()
        if candidate == text or candidate.startswith(text) or text.startswith(candidate[:3]):
            combo.setCurrentIndex(index)
            return
    if combo.isEditable():
        combo.setCurrentText(text)


def _build_edge_page(host: Any) -> QWidget:
    page = QWidget()
    form = QFormLayout(page)
    _prepare_form(host, form)
    host.a14_edge_source = _combo(TRIGGER_SOURCES)
    host.a14_edge_slope = _combo(TRIGGER_SLOPES)
    host.a14_edge_coupling = _combo(TRIGGER_COUPLINGS)
    host.a14_edge_level = QLineEdit("1.0")
    form.addRow("Source", host.a14_edge_source)
    form.addRow("Slope", host.a14_edge_slope)
    form.addRow("Coupling", host.a14_edge_coupling)
    form.addRow("Level", host.a14_edge_level)
    return page


def _refresh_pulse_fields(host: Any) -> None:
    pulse_class = host.a14_pulse_class.currentText().strip().upper()
    width = pulse_class == "WIDTH"
    runt = pulse_class == "RUNT"
    timeout = pulse_class == "TIMEOUT"

    polarity_values = (
        TRIGGER_PULSE_WIDTH_POLARITIES
        if width
        else TRIGGER_PULSE_RUNT_POLARITIES
        if runt
        else TRIGGER_PULSE_TIMEOUT_POLARITIES
    )
    current = host.a14_pulse_polarity.currentText()
    host.a14_pulse_polarity.clear()
    host.a14_pulse_polarity.addItems(polarity_values)
    if current in polarity_values:
        host.a14_pulse_polarity.setCurrentText(current)

    host.a14_pulse_when.setEnabled(width or runt)
    host.a14_pulse_low_limit.setEnabled(width or runt)
    host.a14_pulse_high_limit.setEnabled(width or runt)
    host.a14_pulse_threshold_high.setEnabled(runt)
    host.a14_pulse_threshold_low.setEnabled(runt)
    host.a14_pulse_timeout_time.setEnabled(timeout)

    when_values = TRIGGER_PULSE_WIDTH_WHEN if width else TRIGGER_PULSE_RUNT_WHEN
    current_when = host.a14_pulse_when.currentText()
    host.a14_pulse_when.clear()
    host.a14_pulse_when.addItems(when_values)
    if current_when in when_values:
        host.a14_pulse_when.setCurrentText(current_when)


def _build_pulse_page(host: Any) -> QWidget:
    page = QWidget()
    form = QFormLayout(page)
    _prepare_form(host, form)
    host.a14_pulse_class = _combo(_PULSE_GUI_CLASSES)
    host.a14_pulse_source = _combo(TRIGGER_SOURCES)
    host.a14_pulse_polarity = _combo(TRIGGER_PULSE_WIDTH_POLARITIES)
    host.a14_pulse_when = _combo(TRIGGER_PULSE_WIDTH_WHEN)
    host.a14_pulse_low_limit = QLineEdit("8e-9")
    host.a14_pulse_high_limit = QLineEdit("12e-9")
    host.a14_pulse_threshold_high = QLineEdit("1.0")
    host.a14_pulse_threshold_low = QLineEdit("0.0")
    host.a14_pulse_timeout_time = QLineEdit("1e-6")
    form.addRow("Class", host.a14_pulse_class)
    form.addRow("Source", host.a14_pulse_source)
    form.addRow("Polarity", host.a14_pulse_polarity)
    form.addRow("Comparator", host.a14_pulse_when)
    form.addRow("Low limit s", host.a14_pulse_low_limit)
    form.addRow("High limit s", host.a14_pulse_high_limit)
    form.addRow("High threshold V", host.a14_pulse_threshold_high)
    form.addRow("Low threshold V", host.a14_pulse_threshold_low)
    form.addRow("Timeout s", host.a14_pulse_timeout_time)
    host.a14_pulse_class.currentTextChanged.connect(lambda _text: _refresh_pulse_fields(host))
    _refresh_pulse_fields(host)
    return page


def _refresh_logic_fields(host: Any) -> None:
    logic_class = host.a14_logic_class.currentText().strip().upper()
    pattern = logic_class == "LOGIC"
    sethold = logic_class == "SETHOLD"

    for widget in (
        host.a14_logic_function,
        host.a14_logic_ch1,
        host.a14_logic_ch2,
        host.a14_logic_ch3,
        host.a14_logic_ch4,
        host.a14_logic_when,
    ):
        widget.setEnabled(pattern)
    for widget in (
        host.a14_logic_clock_threshold,
        host.a14_logic_data_threshold,
        host.a14_logic_setup_time,
        host.a14_logic_hold_time,
    ):
        widget.setEnabled(sethold)

    current = host.a14_logic_clock_source.currentText()
    values = list(_ANALOG_SOURCES) + (["NONE"] if pattern else [])
    host.a14_logic_clock_source.clear()
    host.a14_logic_clock_source.addItems(values)
    if current in values:
        host.a14_logic_clock_source.setCurrentText(current)


def _build_logic_page(host: Any) -> QWidget:
    page = QWidget()
    form = QFormLayout(page)
    _prepare_form(host, form)
    host.a14_logic_class = _combo(_LOGIC_GUI_CLASSES)
    host.a14_logic_function = _combo(TRIGGER_LOGIC_FUNCTIONS)
    host.a14_logic_ch1 = _combo(TRIGGER_LOGIC_INPUT_STATES)
    host.a14_logic_ch2 = _combo(TRIGGER_LOGIC_INPUT_STATES)
    host.a14_logic_ch3 = _combo(TRIGGER_LOGIC_INPUT_STATES)
    host.a14_logic_ch4 = _combo(TRIGGER_LOGIC_INPUT_STATES)
    host.a14_logic_clock_source = _combo(list(_ANALOG_SOURCES) + ["NONE"])
    host.a14_logic_clock_edge = _combo(TRIGGER_LOGIC_CLOCK_EDGES)
    host.a14_logic_when = _combo(TRIGGER_LOGIC_PATTERN_WHEN)
    host.a14_logic_clock_threshold = QLineEdit("1.0")
    host.a14_logic_data_threshold = QLineEdit("1.0")
    host.a14_logic_setup_time = QLineEdit("5e-9")
    host.a14_logic_hold_time = QLineEdit("5e-9")
    form.addRow("Class", host.a14_logic_class)
    form.addRow("Function", host.a14_logic_function)
    form.addRow("CH1", host.a14_logic_ch1)
    form.addRow("CH2", host.a14_logic_ch2)
    form.addRow("CH3", host.a14_logic_ch3)
    form.addRow("CH4", host.a14_logic_ch4)
    form.addRow("Clock source", host.a14_logic_clock_source)
    form.addRow("Clock edge", host.a14_logic_clock_edge)
    form.addRow("Pattern condition", host.a14_logic_when)
    form.addRow("Clock threshold V", host.a14_logic_clock_threshold)
    form.addRow("Data threshold V", host.a14_logic_data_threshold)
    form.addRow("Setup time s", host.a14_logic_setup_time)
    form.addRow("Hold time s", host.a14_logic_hold_time)
    host.a14_logic_class.currentTextChanged.connect(lambda _text: _refresh_logic_fields(host))
    _refresh_logic_fields(host)
    return page


def _build_video_page(host: Any) -> QWidget:
    page = QWidget()
    form = QFormLayout(page)
    _prepare_form(host, form)
    host.a14_video_source = _combo(_ANALOG_SOURCES)
    host.a14_video_standard = _combo(TRIGGER_VIDEO_STANDARDS)
    host.a14_video_line = QLineEdit("1")
    host.a14_video_field = _combo(TRIGGER_VIDEO_FIELDS)
    host.a14_video_polarity = _combo(TRIGGER_VIDEO_POLARITIES)
    form.addRow("Source", host.a14_video_source)
    form.addRow("Standard", host.a14_video_standard)
    form.addRow("Line", host.a14_video_line)
    form.addRow("Field", host.a14_video_field)
    form.addRow("Polarity", host.a14_video_polarity)
    return page


def _a_trigger_config(host: Any) -> TriggerConfig:
    trigger_type = host.a14_trigger_type.currentText().strip().upper()
    mode = host.a14_trigger_mode.currentText().strip().upper() or None
    if trigger_type == "EDGE":
        return TriggerConfig(
            trigger_type="EDGE",
            mode=mode,
            source=host.a14_edge_source.currentText(),
            slope=host.a14_edge_slope.currentText(),
            coupling=host.a14_edge_coupling.currentText(),
            level=_text(host.a14_edge_level),
        )
    if trigger_type == "PULSE":
        pulse_class = host.a14_pulse_class.currentText().strip().upper()
        common = dict(
            trigger_type="PULSE",
            pulse_class=pulse_class,
            source=host.a14_pulse_source.currentText(),
            pulse_polarity=host.a14_pulse_polarity.currentText(),
            mode=mode,
        )
        if pulse_class == "WIDTH":
            return TriggerConfig(
                **common,
                pulse_when=host.a14_pulse_when.currentText(),
                pulse_low_limit=_text(host.a14_pulse_low_limit),
                pulse_high_limit=_text(host.a14_pulse_high_limit),
            )
        if pulse_class == "RUNT":
            return TriggerConfig(
                **common,
                pulse_when=host.a14_pulse_when.currentText(),
                pulse_low_limit=_text(host.a14_pulse_low_limit),
                pulse_high_limit=_text(host.a14_pulse_high_limit),
                pulse_threshold_high=_text(host.a14_pulse_threshold_high),
                pulse_threshold_low=_text(host.a14_pulse_threshold_low),
            )
        return TriggerConfig(
            **common,
            pulse_timeout_time=_text(host.a14_pulse_timeout_time),
        )
    if trigger_type == "LOGIC":
        logic_class = host.a14_logic_class.currentText().strip().upper()
        common = dict(
            trigger_type="LOGIC",
            logic_class=logic_class,
            logic_clock_source=host.a14_logic_clock_source.currentText(),
            logic_clock_edge=host.a14_logic_clock_edge.currentText(),
            mode=mode,
        )
        if logic_class == "LOGIC":
            return TriggerConfig(
                **common,
                logic_function=host.a14_logic_function.currentText(),
                logic_input_ch1=host.a14_logic_ch1.currentText(),
                logic_input_ch2=host.a14_logic_ch2.currentText(),
                logic_input_ch3=host.a14_logic_ch3.currentText(),
                logic_input_ch4=host.a14_logic_ch4.currentText(),
                logic_when=host.a14_logic_when.currentText(),
            )
        return TriggerConfig(
            **common,
            logic_clock_threshold=_text(host.a14_logic_clock_threshold),
            logic_data_threshold=_text(host.a14_logic_data_threshold),
            logic_setup_time=_text(host.a14_logic_setup_time),
            logic_hold_time=_text(host.a14_logic_hold_time),
        )
    if trigger_type == "VIDEO":
        return TriggerConfig(
            trigger_type="VIDEO",
            mode=mode,
            video_source=host.a14_video_source.currentText(),
            video_standard=host.a14_video_standard.currentText(),
            video_line=_text(host.a14_video_line),
            video_field=host.a14_video_field.currentText(),
            video_polarity=host.a14_video_polarity.currentText(),
        )
    raise ValueError(f"Unsupported GUI trigger type: {trigger_type!r}")


def _show_a_readback(host: Any, result: object) -> None:
    if not isinstance(result, dict):
        return
    host.a14_trigger_readback.setText(", ".join(f"{key}={value}" for key, value in result.items()))
    trigger_type = str(result.get("trigger_type", "")).upper()
    _set_combo(host.a14_trigger_type, trigger_type)
    if "mode" in result:
        _set_combo(host.a14_trigger_mode, result["mode"])
    holdoff = result.get("holdoff")
    if holdoff is not None:
        host.a14_holdoff.setText(str(holdoff))


def _build_a_trigger_card(host: Any) -> QWidget:
    card = host._card("Advanced A trigger")
    form = QFormLayout(card)
    _prepare_form(host, form)
    host.a14_trigger_type = _combo(_A_TRIGGER_TYPES)
    host.a14_trigger_type.setObjectName("A14TriggerType")
    host.a14_trigger_mode = _combo(TRIGGER_MODES)
    host.a14_holdoff = QLineEdit()
    host.a14_holdoff.setPlaceholderText("leave unchanged")
    host.a14_holdoff.setObjectName("A14TriggerHoldoff")
    host.a14_trigger_pages = QStackedWidget()
    host.a14_trigger_pages.setObjectName("A14TriggerTypeStack")
    host.a14_trigger_pages.addWidget(_build_edge_page(host))
    host.a14_trigger_pages.addWidget(_build_pulse_page(host))
    host.a14_trigger_pages.addWidget(_build_logic_page(host))
    host.a14_trigger_pages.addWidget(_build_video_page(host))
    host.a14_trigger_readback = QLineEdit()
    host.a14_trigger_readback.setReadOnly(True)
    host.a14_trigger_readback.setObjectName("A14TriggerReadback")
    form.addRow("Type", host.a14_trigger_type)
    form.addRow("Mode", host.a14_trigger_mode)
    form.addRow("Type-specific fields", host.a14_trigger_pages)
    form.addRow("Holdoff s", host.a14_holdoff)
    form.addRow("Readback", host.a14_trigger_readback)
    hint = QLabel(
        "BUS and PULSE/TRANSITION stay hidden until their field-level SCPI paths are "
        "hardware-qualified. Holdoff is the verified time-value form only."
    )
    hint.setObjectName("MutedLabel")
    hint.setWordWrap(True)
    form.addRow(hint)

    def type_changed(_text: str) -> None:
        host.a14_trigger_pages.setCurrentIndex(max(0, host.a14_trigger_type.currentIndex()))

    def apply_trigger() -> None:
        config = _a_trigger_config(host)
        holdoff = _text(host.a14_holdoff)

        def action(scope: Any):
            scope.configure_trigger(config, holdoff=holdoff)
            return scope.get_trigger_configuration()

        host._run_action(
            "Applying advanced trigger",
            action,
            on_success=lambda result: _show_a_readback(host, result),
        )

    def read_trigger() -> None:
        host._run_action(
            "Reading advanced trigger",
            lambda scope: scope.get_trigger_configuration(),
            on_success=lambda result: _show_a_readback(host, result),
        )

    host.a14_trigger_type.currentTextChanged.connect(type_changed)
    type_changed(host.a14_trigger_type.currentText())
    buttons = QHBoxLayout()
    buttons.addWidget(host._button("Read trigger", read_trigger))
    buttons.addWidget(host._accent_button("Apply trigger", apply_trigger))
    form.addRow(buttons)
    return _prepare_card(host, card)


def _refresh_sequence_fields(host: Any) -> None:
    by_events = host.a14_b_by.currentText().strip().upper() == "EVENTS"
    host.a14_b_events.setEnabled(by_events)
    host.a14_b_time.setEnabled(not by_events)


def _show_b_readback(host: Any, result: object) -> None:
    if isinstance(result, dict):
        host.a14_b_readback.setText(", ".join(f"{key}={value}" for key, value in result.items()))


def _build_sequence_card(host: Any) -> QWidget:
    card = host._card("Sequence / B trigger")
    form = QFormLayout(card)
    _prepare_form(host, form)
    host.a14_b_state = QCheckBox("Enable B trigger")
    host.a14_b_state.setObjectName("A14BTriggerState")
    host.a14_b_source = _combo(TRIGGER_SOURCES)
    host.a14_b_slope = _combo(TRIGGER_SLOPES)
    host.a14_b_coupling = _combo(TRIGGER_COUPLINGS)
    host.a14_b_level = QLineEdit("1.0")
    host.a14_b_by = _combo(TRIGGER_SEQUENCE_BY)
    host.a14_b_time = QLineEdit("1e-6")
    host.a14_b_events = QLineEdit("1")
    host.a14_b_readback = QLineEdit()
    host.a14_b_readback.setReadOnly(True)
    form.addRow(host.a14_b_state)
    form.addRow("Source", host.a14_b_source)
    form.addRow("Slope", host.a14_b_slope)
    form.addRow("Coupling", host.a14_b_coupling)
    form.addRow("Level", host.a14_b_level)
    form.addRow("Delay by", host.a14_b_by)
    form.addRow("Delay s", host.a14_b_time)
    form.addRow("Event count", host.a14_b_events)
    form.addRow("Readback", host.a14_b_readback)
    hint = QLabel("The DPO4054 accepts B-trigger enable only while A is EDGE.")
    hint.setObjectName("MutedLabel")
    hint.setWordWrap(True)
    form.addRow(hint)

    def apply_sequence() -> None:
        by = host.a14_b_by.currentText().strip().upper()
        config = SequenceTriggerConfig(
            state=host.a14_b_state.isChecked(),
            source=host.a14_b_source.currentText(),
            slope=host.a14_b_slope.currentText(),
            coupling=host.a14_b_coupling.currentText(),
            level=_text(host.a14_b_level),
            by=by,
            time=_text(host.a14_b_time) if by == "TIME" else None,
            events_count=_text(host.a14_b_events) if by == "EVENTS" else None,
        )

        def action(scope: Any):
            scope.configure_sequence_trigger(config)
            return scope.get_sequence_trigger_configuration()

        host._run_action(
            "Applying B trigger",
            action,
            on_success=lambda result: _show_b_readback(host, result),
        )

    def read_sequence() -> None:
        host._run_action(
            "Reading B trigger",
            lambda scope: scope.get_sequence_trigger_configuration(),
            on_success=lambda result: _show_b_readback(host, result),
        )

    host.a14_b_by.currentTextChanged.connect(lambda _text: _refresh_sequence_fields(host))
    _refresh_sequence_fields(host)
    buttons = QHBoxLayout()
    buttons.addWidget(host._button("Read B trigger", read_sequence))
    buttons.addWidget(host._accent_button("Apply B trigger", apply_sequence))
    form.addRow(buttons)
    return _prepare_card(host, card)


def _section(host: Any, title: str, widget: QWidget) -> QWidget:
    builder = getattr(host, "_collapsible_section", None)
    if callable(builder):
        return builder(title, widget)
    return widget


def build_trigger_page(host: Any) -> QWidget:
    """Build the production Trigger page at the composition boundary."""
    body = QWidget()
    body.setObjectName("A14TriggerScrollBody")
    layout = QVBoxLayout(body)
    layout.setContentsMargins(0, 0, 8, 0)
    layout.setSpacing(12)

    # Preserve established trigger/acquisition controls while replacing the old
    # edge-only setup card with the A14 type-aware public-driver configuration.
    if callable(getattr(host, "_build_trigger_acquisition_toolbar", None)):
        layout.addWidget(host._build_trigger_acquisition_toolbar())
    if callable(getattr(host, "_build_trigger_level_only_card", None)):
        layout.addWidget(host._build_trigger_level_only_card())
    if callable(getattr(host, "_build_horizontal_position_card", None)):
        layout.addWidget(_section(host, "Horizontal position", host._build_horizontal_position_card()))

    layout.addWidget(_section(host, "Advanced A trigger", _build_a_trigger_card(host)))
    layout.addWidget(_section(host, "Sequence / B trigger", _build_sequence_card(host)))

    if callable(getattr(host, "_build_image_rearm_card", None)):
        layout.addWidget(_section(host, "Image capture re-arm", host._build_image_rearm_card()))
    layout.addStretch(1)

    wrapper = getattr(host, "_wrap_scrollable_drawer_page", None)
    if callable(wrapper):
        return wrapper(
            body,
            scroll_name="A14TriggerScrollArea",
            body_name="A14TriggerScrollBody",
        )
    return body


__all__ = ["build_trigger_page"]
