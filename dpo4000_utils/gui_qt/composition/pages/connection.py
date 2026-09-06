"""Native composed Connection page for the v0.8 production surface."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ....connection import visaResourceAddr


def _connect_stale_tracking(host: Any) -> None:
    """Preserve the mature connection-invalidating UI behavior."""
    stale = getattr(host, "_mark_connection_stale", None)
    if not callable(stale):
        return

    host.resource.currentTextChanged.connect(
        lambda _text: stale("Resource changed")
    )
    host.eth_host.textChanged.connect(
        lambda _text: stale("Ethernet host changed")
    )
    host.eth_port.textChanged.connect(
        lambda _text: stale("Ethernet port changed")
    )
    host.eth_protocol.currentTextChanged.connect(
        lambda _text: stale("Ethernet protocol changed")
    )
    host.usb_mode.toggled.connect(
        lambda _checked: stale("Connection mode changed")
    )
    host.eth_mode.toggled.connect(
        lambda _checked: stale("Connection mode changed")
    )


def _add_keep_session_options(host: Any, page: QWidget) -> None:
    """Preserve the v0.7 worker-owned retained-session preference controls."""
    options_card = host._card("Connection options")
    form = QFormLayout(options_card)
    prepare_form = getattr(host, "_prepare_form", None)
    if callable(prepare_form):
        prepare_form(form)

    host.keep_session = QCheckBox("Keep session")
    host.keep_session.setChecked(True)
    host.keep_session.setToolTip(
        "Recommended: keep one worker-owned VISA connection open and reuse it "
        "across scope operations. Disable only when a backend requires reconnecting "
        "after every operation."
    )
    form.addRow(host.keep_session)

    hint = QLabel(
        "Enabled (recommended): reuse one serialized worker-owned VISA session. "
        "Disabled: the same worker closes the scope after each completed operation."
    )
    hint.setObjectName("MutedLabel")
    hint.setWordWrap(True)
    form.addRow(hint)

    layout = page.layout()
    if layout is not None:
        insert_index = max(0, layout.count() - 1)
        layout.insertWidget(insert_index, options_card)


def build_connection_page(host: Any) -> QWidget:
    """Build the production Connection page without inheriting a window builder."""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setSpacing(10)

    card = host._card("Connection")
    form = QFormLayout(card)

    mode_box = QWidget()
    mode_layout = QHBoxLayout(mode_box)
    mode_layout.setContentsMargins(0, 0, 0, 0)
    host.usb_mode = QRadioButton("USB / VISA")
    host.eth_mode = QRadioButton("Ethernet")
    host.usb_mode.setChecked(True)
    host.usb_mode.toggled.connect(
        lambda checked: checked and host._on_connection_mode_changed()
    )
    host.eth_mode.toggled.connect(
        lambda checked: checked and host._on_connection_mode_changed()
    )
    mode_layout.addWidget(host.usb_mode)
    mode_layout.addWidget(host.eth_mode)
    mode_layout.addStretch(1)
    form.addRow("Mode", mode_box)

    resource_box = QWidget()
    resource_layout = QHBoxLayout(resource_box)
    resource_layout.setContentsMargins(0, 0, 0, 0)
    resource_layout.setSpacing(8)
    host.resource = QComboBox()
    host.resource.setEditable(True)
    host.resource.addItem(visaResourceAddr)
    resource_layout.addWidget(host.resource, 1)
    resource_layout.addWidget(host._button("Refresh", host.refresh_visa_resources))
    form.addRow("VISA resource", resource_box)

    host.eth_host = QLineEdit()
    host.eth_port = QLineEdit("4000")
    host.eth_protocol = QComboBox()
    host.eth_protocol.addItems(["VXI-11 / INSTR", "Raw SOCKET"])
    host.generated_resource = QLineEdit()
    host.generated_resource.setReadOnly(True)
    host.timeout_ms = QLineEdit("20000")
    host.eth_host.textChanged.connect(
        lambda _text: host._refresh_generated_ethernet_resource()
    )
    host.eth_port.textChanged.connect(
        lambda _text: host._refresh_generated_ethernet_resource()
    )
    host.eth_protocol.currentTextChanged.connect(
        lambda _text: host._refresh_generated_ethernet_resource()
    )
    form.addRow("Ethernet IP/host", host.eth_host)
    form.addRow("Protocol", host.eth_protocol)
    form.addRow("Socket port", host.eth_port)
    form.addRow("Generated resource", host.generated_resource)
    form.addRow("Timeout ms", host.timeout_ms)

    ethernet_button_row = QHBoxLayout()
    ethernet_button_row.addWidget(
        host._button("Use Ethernet resource", host.apply_ethernet_resource)
    )
    ethernet_button_row.addWidget(host._accent_button("Test IDN", host.test_connection))
    form.addRow(ethernet_button_row)

    hint = QLabel(
        "VXI-11: TCPIP0::<ip>::INSTR. Socket: TCPIP0::<ip>::4000::SOCKET."
    )
    hint.setObjectName("MutedLabel")
    hint.setWordWrap(True)
    form.addRow(hint)

    layout.addWidget(card)
    layout.addStretch(1)

    _connect_stale_tracking(host)
    _add_keep_session_options(host, page)
    return page


__all__ = ["build_connection_page"]
