"""Experimental GTK4 main window for the DPO4000 utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk  # noqa: E402

from ..connection import visaResourceAddr
from ..control import MEASUREMENT_SOURCES, MEASUREMENT_TYPES_BY_GROUP, MeasurementConfig
from ..hardcopy import save_screen_png
from ..instrument import DPO4054

APP_ID = "io.github.ami3go.dpo4000.gtk"
APP_TITLE = "Tektronix DPO4000 GTK4 Prototype"
DEFAULT_OUTPUT_FOLDER = Path("scope_output")
GTK_THEME_FILE = "theme.css"
TRIGGER_CHANNELS = ("1", "2", "3", "4")
TRIGGER_MODES = ("AUTO", "NORMAL")
TRIGGER_SOURCES = ("CH1", "CH2", "CH3", "CH4", "AUX", "LINE")
TRIGGER_SLOPES = ("RISE", "FALL", "EITHER")
TRIGGER_COUPLINGS = ("DC", "AC", "HFREJ", "LFREJ", "NOISEREJ")


def run() -> int:
    """Run the GTK4 application."""
    app = GtkScopeApplication()
    return app.run(None)


class GtkScopeApplication(Gtk.Application):
    """GTK application wrapper."""

    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_activate(self) -> None:  # noqa: N802 - GTK virtual method name
        load_css_theme()
        window = GtkScopeWindow(application=self)
        window.present()


class GtkScopeWindow(Gtk.ApplicationWindow):
    """First-pass GTK4 GUI for comparison against Tk/PySide6."""

    def __init__(self, *, application: Gtk.Application) -> None:
        super().__init__(application=application, title=APP_TITLE)
        self.set_default_size(1280, 760)
        self.output_folder = DEFAULT_OUTPUT_FOLDER
        self.output_folder.mkdir(parents=True, exist_ok=True)
        self.last_image_path: Path | None = None

        self.mode_usb = Gtk.CheckButton(label="USB / VISA")
        self.mode_eth = Gtk.CheckButton(label="Ethernet")
        self.mode_eth.set_group(self.mode_usb)
        self.mode_usb.set_active(True)

        self.resource_entry = Gtk.Entry(text=visaResourceAddr)
        self.eth_host_entry = Gtk.Entry()
        self.eth_port_entry = Gtk.Entry(text="4000")
        self.protocol_combo = string_dropdown(("VXI-11 / INSTR", "Raw SOCKET"), selected=0)
        self.timeout_entry = Gtk.Entry(text="5000")

        self.preview_image = Gtk.Picture()
        self.preview_label = Gtk.Label(label="Capture preview to show scope screen here.")
        self.status_label = Gtk.Label(label="Ready. GTK4 prototype uses short-lived VISA sessions.")
        self.status_label.add_css_class("status-bar")
        self.log_buffer = Gtk.TextBuffer()

        self.measurement_slot = Gtk.SpinButton.new_with_range(1, 8, 1)
        self.measurement_group = string_dropdown(tuple(MEASUREMENT_TYPES_BY_GROUP), selected=0)
        self.measurement_type = Gtk.Entry(text=MEASUREMENT_TYPES_BY_GROUP["Amplitude"][0])
        self.measurement_source1 = string_dropdown(MEASUREMENT_SOURCES, selected=0)
        self.measurement_source2 = string_dropdown(("",) + MEASUREMENT_SOURCES, selected=0)
        self.measurement_value = Gtk.Entry()
        self.measurement_value.set_editable(False)

        self.trigger_channel = string_dropdown(TRIGGER_CHANNELS, selected=0)
        self.trigger_level = Gtk.Entry(text="1.0")
        self.horizontal_position = Gtk.Entry(text="0")
        self.edge_mode = string_dropdown(TRIGGER_MODES, selected=0)
        self.edge_source = string_dropdown(TRIGGER_SOURCES, selected=0)
        self.edge_slope = string_dropdown(TRIGGER_SLOPES, selected=0)
        self.edge_coupling = string_dropdown(TRIGGER_COUPLINGS, selected=0)
        self.edge_level = Gtk.Entry(text="1.0")

        self.set_child(self._build_root())
        self.measurement_group.connect("notify::selected", self._on_measurement_group_changed)

    def _build_root(self) -> Gtk.Widget:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_top(16)
        root.set_margin_bottom(16)
        root.set_margin_start(16)
        root.set_margin_end(16)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        title = Gtk.Label(label=APP_TITLE)
        title.add_css_class("header-title")
        title.set_xalign(0)
        subtitle = Gtk.Label(label="Experimental branch · Tk GUI remains unchanged")
        subtitle.add_css_class("muted")
        subtitle.set_xalign(1)
        header.append(title)
        header.append(subtitle)
        header.set_hexpand(True)
        title.set_hexpand(True)
        root.append(header)

        content = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        content.set_start_child(self._build_preview_card())
        content.set_end_child(self._build_tabs())
        content.set_resize_start_child(True)
        content.set_resize_end_child(True)
        content.set_shrink_start_child(False)
        content.set_shrink_end_child(False)
        content.set_position(760)
        root.append(content)

        root.append(self.status_label)
        return root

    def _build_preview_card(self) -> Gtk.Widget:
        card = card_box()
        title = section_title("Screen preview")
        card.append(title)

        preview_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        preview_box.add_css_class("preview-box")
        preview_box.set_vexpand(True)
        preview_box.set_hexpand(True)
        preview_box.set_margin_top(8)
        preview_box.set_margin_bottom(10)
        preview_box.set_margin_start(4)
        preview_box.set_margin_end(4)
        self.preview_image.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.preview_image.set_vexpand(True)
        self.preview_image.set_hexpand(True)
        preview_box.append(self.preview_image)
        preview_box.append(self.preview_label)
        card.append(preview_box)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        buttons.append(button("Capture preview", self.capture_preview, suggested=True))
        buttons.append(button("Copy preview", self.copy_preview_to_clipboard))
        card.append(buttons)
        return card

    def _build_tabs(self) -> Gtk.Widget:
        notebook = Gtk.Notebook()
        notebook.set_hexpand(True)
        notebook.set_vexpand(True)
        notebook.append_page(self._build_connection_tab(), Gtk.Label(label="Connection"))
        notebook.append_page(self._build_channels_tab(), Gtk.Label(label="Channels"))
        notebook.append_page(self._build_measurement_tab(), Gtk.Label(label="Measurement"))
        notebook.append_page(self._build_trigger_tab(), Gtk.Label(label="Trigger"))
        notebook.append_page(self._build_settings_tab(), Gtk.Label(label="Settings"))
        notebook.append_page(self._build_log_tab(), Gtk.Label(label="Log"))
        return notebook

    def _build_connection_tab(self) -> Gtk.Widget:
        box = tab_box()
        card = card_box()
        card.append(section_title("Connection"))

        mode_row = row_box()
        mode_row.append(Gtk.Label(label="Mode"))
        mode_row.append(self.mode_usb)
        mode_row.append(self.mode_eth)
        card.append(mode_row)

        card.append(labeled_widget("VISA resource", self.resource_entry))
        card.append(labeled_widget("Ethernet IP/host", self.eth_host_entry))
        card.append(labeled_widget("Protocol", self.protocol_combo))
        card.append(labeled_widget("Socket port", self.eth_port_entry))
        card.append(labeled_widget("Timeout ms", self.timeout_entry))
        card.append(button("Test IDN", self.test_idn, suggested=True))
        box.append(card)
        return box

    def _build_channels_tab(self) -> Gtk.Widget:
        box = tab_box()
        card = card_box()
        card.append(section_title("Channels"))
        card.append(muted_label("GTK4 branch scaffold: channel label read/write can be ported next."))
        box.append(card)
        return box

    def _build_measurement_tab(self) -> Gtk.Widget:
        box = tab_box()
        card = card_box()
        card.append(section_title("Measurement"))
        card.append(muted_label("Add/update displayed MEAS1..MEAS8 readouts."))
        card.append(labeled_widget("Slot", self.measurement_slot))
        card.append(labeled_widget("Group", self.measurement_group))
        card.append(labeled_widget("Measurement type", self.measurement_type))
        card.append(labeled_widget("Source 1", self.measurement_source1))
        card.append(labeled_widget("Source 2", self.measurement_source2))

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        buttons.append(button("Add / update", self.add_measurement, suggested=True))
        buttons.append(button("Read value", self.read_measurement_value))
        buttons.append(button("Clear slot", self.clear_measurement_slot))
        card.append(buttons)
        card.append(labeled_widget("Last read value", self.measurement_value))
        box.append(card)
        return box

    def _build_trigger_tab(self) -> Gtk.Widget:
        box = tab_box()

        actions = card_box()
        actions.append(section_title("Acquisition / trigger actions"))
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.append(button("Run", lambda: self.control_action("Starting acquisition", lambda s: s.run_acquisition())))
        row.append(button("Stop", lambda: self.control_action("Stopping acquisition", lambda s: s.stop_acquisition())))
        row.append(button("Single", lambda: self.control_action("Single acquisition", lambda s: s.single_acquisition())))
        row.append(button("Continuous", lambda: self.control_action("Continuous acquisition", lambda s: s.continuous_acquisition())))
        actions.append(row)
        actions.append(button("Force trigger", lambda: self.control_action("Forcing trigger", lambda s: s.force_trigger_event()), suggested=True))
        box.append(actions)

        level = card_box()
        level.append(section_title("Trigger level"))
        level.append(labeled_widget("Channel", self.trigger_channel))
        level.append(labeled_widget("Level", self.trigger_level))
        level.append(button("Set trigger level", self.set_trigger_level, suggested=True))
        box.append(level)

        horizontal = card_box()
        horizontal.append(section_title("Horizontal trigger position"))
        horizontal.append(labeled_widget("Position", self.horizontal_position))
        horizontal.append(button("Set horizontal position", self.set_horizontal_position, suggested=True))
        box.append(horizontal)

        edge = card_box()
        edge.append(section_title("Edge trigger setup"))
        edge.append(labeled_widget("Mode", self.edge_mode))
        edge.append(labeled_widget("Source", self.edge_source))
        edge.append(labeled_widget("Slope", self.edge_slope))
        edge.append(labeled_widget("Coupling", self.edge_coupling))
        edge.append(labeled_widget("Level", self.edge_level))
        edge.append(button("Apply edge trigger", self.apply_edge_trigger, suggested=True))
        box.append(edge)
        return box

    def _build_settings_tab(self) -> Gtk.Widget:
        box = tab_box()
        card = card_box()
        card.append(section_title("Settings"))
        card.append(muted_label("GTK4 branch scaffold: persistent preferences can be ported next."))
        box.append(card)
        return box

    def _build_log_tab(self) -> Gtk.Widget:
        box = tab_box()
        view = Gtk.TextView(buffer=self.log_buffer)
        view.set_editable(False)
        view.set_monospace(True)
        view.add_css_class("log-view")
        scroller = Gtk.ScrolledWindow()
        scroller.set_child(view)
        scroller.set_vexpand(True)
        scroller.set_hexpand(True)
        box.append(scroller)
        return box

    def selected_resource_name(self) -> str:
        if self.mode_eth.get_active():
            host = self.eth_host_entry.get_text().strip()
            port = self.eth_port_entry.get_text().strip() or "4000"
            protocol = dropdown_text(self.protocol_combo)
            if not host:
                raise ValueError("Ethernet host/IP is required.")
            if protocol == "Raw SOCKET":
                return f"TCPIP0::{host}::{port}::SOCKET"
            return f"TCPIP0::{host}::INSTR"
        return self.resource_entry.get_text().strip() or visaResourceAddr

    def with_scope(self, description: str, operation: Callable[[DPO4054], object]) -> object | None:
        self.set_status(description)
        try:
            with DPO4054(self.selected_resource_name(), auto_connect=True) as scope:
                result = operation(scope)
        except Exception as exc:
            self.log(f"ERROR: {description}: {exc}")
            self.set_status(f"Failed: {description}")
            return None
        self.log(f"OK: {description}")
        self.set_status(f"Done: {description}")
        return result

    def test_idn(self) -> None:
        result = self.with_scope("Reading *IDN?", lambda scope: scope.scope.query("*IDN?").strip())
        if result:
            self.log(str(result))

    def capture_preview(self) -> None:
        path = self.output_folder / "gtk_scope_screen.png"
        result = self.with_scope("Capturing scope preview", lambda scope: save_screen_png(scope.scope, path))
        if result:
            self.last_image_path = Path(result)
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(str(self.last_image_path))
                texture = Gdk.Texture.new_for_pixbuf(pixbuf)
                self.preview_image.set_paintable(texture)
                self.preview_label.set_label(str(self.last_image_path))
            except Exception as exc:
                self.log(f"ERROR: Could not display preview: {exc}")

    def copy_preview_to_clipboard(self) -> None:
        if self.last_image_path is None or not self.last_image_path.exists():
            self.log("No preview image is available to copy.")
            return
        try:
            texture = Gdk.Texture.new_from_filename(str(self.last_image_path))
            clipboard = self.get_clipboard()
            clipboard.set_texture(texture)
            self.set_status("Preview copied to clipboard")
        except Exception as exc:
            self.log(f"ERROR: Clipboard copy failed: {exc}")

    def add_measurement(self) -> None:
        slot = int(self.measurement_slot.get_value())
        config = MeasurementConfig(
            slot=slot,
            measurement_type=self.measurement_type.get_text().strip(),
            source1=dropdown_text(self.measurement_source1),
            source2=dropdown_text(self.measurement_source2) or None,
        )
        self.with_scope(f"Adding MEAS{slot}", lambda scope: scope.add_measurement(config))

    def read_measurement_value(self) -> None:
        slot = int(self.measurement_slot.get_value())
        value = self.with_scope(f"Reading MEAS{slot}", lambda scope: scope.read_measurement_value(slot))
        if value is not None:
            self.measurement_value.set_text(str(value))

    def clear_measurement_slot(self) -> None:
        slot = int(self.measurement_slot.get_value())
        self.with_scope(f"Clearing MEAS{slot}", lambda scope: scope.disable_measurement(slot))

    def set_trigger_level(self) -> None:
        channel = int(dropdown_text(self.trigger_channel))
        level = self.trigger_level.get_text().strip()
        self.with_scope(f"Setting trigger level CH{channel}", lambda scope: scope.set_trigger_level(level, channel=channel))

    def set_horizontal_position(self) -> None:
        position = self.horizontal_position.get_text().strip()
        self.with_scope("Setting horizontal position", lambda scope: scope.set_horizontal_position(position))

    def apply_edge_trigger(self) -> None:
        self.with_scope(
            "Applying edge trigger setup",
            lambda scope: scope.configure_edge_trigger(
                mode=dropdown_text(self.edge_mode),
                source=dropdown_text(self.edge_source),
                slope=dropdown_text(self.edge_slope),
                coupling=dropdown_text(self.edge_coupling),
                level=self.edge_level.get_text().strip(),
            ),
        )

    def control_action(self, description: str, operation: Callable[[DPO4054], object]) -> None:
        self.with_scope(description, operation)

    def _on_measurement_group_changed(self, _dropdown, _param) -> None:
        group = dropdown_text(self.measurement_group)
        choices = MEASUREMENT_TYPES_BY_GROUP.get(group)
        if choices:
            self.measurement_type.set_text(choices[0])

    def set_status(self, message: str) -> None:
        self.status_label.set_label(message)

    def log(self, message: str) -> None:
        end = self.log_buffer.get_end_iter()
        self.log_buffer.insert(end, f"{message}\n")


def load_css_theme() -> None:
    provider = Gtk.CssProvider()
    css_path = Path(__file__).with_name(GTK_THEME_FILE)
    try:
        provider.load_from_path(str(css_path))
    except GLib.Error:
        return
    display = Gdk.Display.get_default()
    if display is not None:
        Gtk.StyleContext.add_provider_for_display(
            display,
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )


def card_box() -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.add_css_class("card")
    box.set_margin_top(6)
    box.set_margin_bottom(6)
    box.set_margin_start(6)
    box.set_margin_end(6)
    return box


def tab_box() -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.set_margin_top(8)
    box.set_margin_bottom(8)
    box.set_margin_start(8)
    box.set_margin_end(8)
    return box


def row_box() -> Gtk.Box:
    return Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)


def section_title(text: str) -> Gtk.Label:
    label = Gtk.Label(label=text)
    label.add_css_class("section-title")
    label.set_xalign(0)
    return label


def muted_label(text: str) -> Gtk.Label:
    label = Gtk.Label(label=text)
    label.add_css_class("muted")
    label.set_wrap(True)
    label.set_xalign(0)
    return label


def labeled_widget(label_text: str, widget: Gtk.Widget) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    label = Gtk.Label(label=label_text)
    label.set_xalign(0)
    box.append(label)
    box.append(widget)
    return box


def button(label: str, callback: Callable[[], None], *, suggested: bool = False) -> Gtk.Button:
    control = Gtk.Button(label=label)
    if suggested:
        control.add_css_class("suggested-action")
    control.connect("clicked", lambda _button: callback())
    return control


def string_dropdown(values: tuple[str, ...], *, selected: int = 0) -> Gtk.DropDown:
    model = Gtk.StringList.new(list(values))
    dropdown = Gtk.DropDown.new(model, None)
    dropdown.set_selected(selected)
    return dropdown


def dropdown_text(dropdown: Gtk.DropDown) -> str:
    selected = dropdown.get_selected_item()
    if selected is None:
        return ""
    return selected.get_string()


__all__ = [
    "APP_ID",
    "APP_TITLE",
    "GtkScopeApplication",
    "GtkScopeWindow",
    "run",
]
