"""
Modern Tkinter GUI for Tektronix DPO4054 / DPO4000 scopes.

Version: v13 output folder and per-file-type naming settings

Features
--------
- Read and set CH1..CH4 labels.
- Capture current oscilloscope screen image as PNG.
- Preview the latest captured image in the GUI.
- Save enabled channel waveform data into one CSV file.
- Save current oscilloscope settings to JSON using DPO4054.save_scope_settings().
- Restore oscilloscope settings from JSON, even if the base driver does not expose
  apply_scope_settings() as an active method.
- Pick VISA resource from a discovered list, with manual entry kept as backup.
- Ethernet connection mode with VXI-11/INSTR and raw SOCKET VISA resource generation.
- Robust scope image capture that strips SCPI block/text prefixes and validates PNG bytes.
- Window/app icon support. Put an authorized custom .ico next to this file if needed.
- Set and read custom A trigger level from the GUI.
- Auto-scale the scope image preview to the available GUI area.
- Right-side tabbed controls with Connection first, then labels, trigger, settings, and log.
- Image/CSV actions are placed below the screen preview so capture/export controls are always near the image.
- Connection controls moved from the top header area into the first right-side tab.
- Settings tab controls destination folder, filename prefix/base, and timestamp options for PNG, CSV, and JSON setup files.

Design note
-----------
This GUI deliberately does NOT keep the VISA/USB connection open while idle.
Each action opens the VISA resource, performs the command, then closes it.
That reduces the chance of blocking TekScope, OpenChoice, or other VISA software.

Expected file layout
--------------------
Place this file next to your existing tektronix_utils.py.

Run
---
    python tektronix_scope_gui_v13_output_naming.py
"""

from __future__ import annotations

import json
import math
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk
from tkinter import ttk

try:
    from PIL import Image, ImageTk
except Exception:  # Pillow is optional. Tkinter fallback still works.
    Image = None
    ImageTk = None

try:
    import pyvisa
    from pyvisa.errors import VisaIOError
except Exception:  # GUI can still open and show a clear error later.
    pyvisa = None
    VisaIOError = Exception

try:
    from tektronix_utils import DPO4054, visaResourceAddr
except Exception as exc:  # Do not crash before GUI appears.
    DPO4054 = None
    visaResourceAddr = "USB0::0x0699::0x0401::C011280::INSTR"
    DRIVER_IMPORT_ERROR = exc
else:
    DRIVER_IMPORT_ERROR = None


APP_TITLE = "Tektronix DPO4054 Utility"
DEFAULT_TIMEOUT_MS = 20_000
DEFAULT_RESTORE_TIMEOUT_MS = 60_000

# Icon lookup order. You may place your own authorized company/product icon
# next to this file using one of these names. The bundled dpo_scope_icon.* files
# are neutral oscilloscope icons, not official Tektronix artwork.
APP_ICON_CANDIDATES = (
    "tektronix_icon.ico",
    "tektronix_icon.png",
    "app_icon.ico",
    "app_icon.png",
    "dpo_scope_icon.ico",
    "dpo_scope_icon.png",
)


@dataclass
class JobResult:
    ok: bool
    message: str
    payload: object | None = None


class ScopeGui(tk.Tk):
    """Main GUI application."""

    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1240x760")
        self.minsize(1040, 620)
        self._set_window_icon()

        self.output_folder = Path.cwd() / "scope_gui_output"
        self.output_folder.mkdir(parents=True, exist_ok=True)

        self._result_queue: queue.Queue[JobResult] = queue.Queue()
        self._busy = False
        self._preview_image: object | None = None
        self._last_image_path: Path | None = None
        self._preview_resize_job: str | None = None

        self._build_style()
        self._build_variables()
        self._build_layout()
        self._poll_result_queue()

        if DRIVER_IMPORT_ERROR is not None:
            self._append_log(
                "Driver import problem. Put tektronix_scope_gui.py next to tektronix_utils.py.\n"
                f"Import error: {DRIVER_IMPORT_ERROR}"
            )

    def _set_window_icon(self) -> None:
        """Set a window/taskbar icon if an icon file is available."""
        base_dir = Path(__file__).resolve().parent
        self._app_icon_image = None

        for icon_name in APP_ICON_CANDIDATES:
            icon_path = base_dir / icon_name
            if not icon_path.exists():
                continue

            try:
                if icon_path.suffix.lower() == ".ico":
                    # Best result on Windows taskbar/titlebar.
                    self.iconbitmap(default=str(icon_path))
                    return

                if icon_path.suffix.lower() == ".png":
                    # Works on Tk 8.6+. Keep a reference to avoid garbage collection.
                    self._app_icon_image = tk.PhotoImage(file=str(icon_path))
                    self.iconphoto(True, self._app_icon_image)
                    return
            except tk.TclError:
                # Try the next icon candidate if this file cannot be loaded.
                continue

    # ---------------------------------------------------------------------
    # UI construction
    # ---------------------------------------------------------------------
    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        self.configure(bg="#111827")

        style.configure("TFrame", background="#111827")
        style.configure("Card.TFrame", background="#1f2937", relief="flat")
        style.configure("TLabel", background="#111827", foreground="#e5e7eb", font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background="#111827", foreground="#9ca3af", font=("Segoe UI", 9))
        style.configure("Card.TLabel", background="#1f2937", foreground="#e5e7eb", font=("Segoe UI", 10))
        style.configure("Title.TLabel", background="#111827", foreground="#ffffff", font=("Segoe UI Semibold", 18))
        style.configure("Section.TLabel", background="#1f2937", foreground="#ffffff", font=("Segoe UI Semibold", 12))
        style.configure("Status.TLabel", background="#0f172a", foreground="#93c5fd", font=("Segoe UI", 9))

        style.configure(
            "Accent.TButton",
            background="#2563eb",
            foreground="#ffffff",
            borderwidth=0,
            focusthickness=0,
            padding=(12, 8),
            font=("Segoe UI Semibold", 10),
        )
        style.map("Accent.TButton", background=[("active", "#1d4ed8"), ("disabled", "#475569")])

        style.configure(
            "TButton",
            background="#374151",
            foreground="#f9fafb",
            borderwidth=0,
            focusthickness=0,
            padding=(10, 7),
            font=("Segoe UI", 10),
        )
        style.map("TButton", background=[("active", "#4b5563"), ("disabled", "#374151")])

        style.configure(
            "TEntry",
            fieldbackground="#0f172a",
            foreground="#f9fafb",
            borderwidth=1,
            insertcolor="#f9fafb",
            padding=6,
        )
        style.configure(
            "TCombobox",
            fieldbackground="#0f172a",
            foreground="#f9fafb",
            borderwidth=1,
            padding=6,
        )
        style.configure("TCheckbutton", background="#1f2937", foreground="#e5e7eb", font=("Segoe UI", 10))
        style.map("TCheckbutton", background=[("active", "#1f2937")])

        style.configure("TNotebook", background="#111827", borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background="#374151",
            foreground="#e5e7eb",
            padding=(14, 8),
            font=("Segoe UI Semibold", 9),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", "#2563eb"), ("active", "#4b5563")],
            foreground=[("selected", "#ffffff"), ("active", "#ffffff")],
        )

    def _build_variables(self) -> None:
        self.connection_mode_var = tk.StringVar(value="visa")
        self.resource_var = tk.StringVar(value=visaResourceAddr)
        self.eth_host_var = tk.StringVar(value="")
        self.eth_port_var = tk.StringVar(value="4000")
        self.eth_protocol_var = tk.StringVar(value="VXI-11 / INSTR")
        self.generated_resource_var = tk.StringVar(value="")
        self.timeout_var = tk.StringVar(value=str(DEFAULT_TIMEOUT_MS))
        self.trigger_channel_var = tk.StringVar(value="")
        self.trigger_setup_channel_var = tk.StringVar(value="1")
        self.trigger_level_var = tk.StringVar(value="1.0")
        self.trigger_readback_var = tk.StringVar(value="")
        self.trigger_set_source_var = tk.BooleanVar(value=True)
        self.restore_wait_opc_var = tk.BooleanVar(value=False)
        self.rearm_after_image_var = tk.BooleanVar(value=True)

        # Output and filename settings. These are controlled from the Settings tab.
        # Final filename format is:
        #   <prefix><base><_YYYYMMDD_HHMMSS if enabled>.<extension>
        self.output_folder_var = tk.StringVar(value=str(self.output_folder))
        self.png_prefix_var = tk.StringVar(value="scope_")
        self.png_base_var = tk.StringVar(value="screen")
        self.png_add_timestamp_var = tk.BooleanVar(value=True)
        self.csv_prefix_var = tk.StringVar(value="scope_")
        self.csv_base_var = tk.StringVar(value="waveform")
        self.csv_add_timestamp_var = tk.BooleanVar(value=True)
        self.settings_prefix_var = tk.StringVar(value="dpo4054_")
        self.settings_base_var = tk.StringVar(value="setup")
        self.settings_add_timestamp_var = tk.BooleanVar(value=True)

        self.label_vars = {ch: tk.StringVar(value="") for ch in range(1, 5)}
        self.status_var = tk.StringVar(
            value="Ready. VISA connection is opened only during each operation and then released."
        )

    def _build_layout(self) -> None:
        root = ttk.Frame(self, padding=18)
        root.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(root)
        header.pack(fill=tk.X)
        ttk.Label(header, text=APP_TITLE, style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Label(
            header,
            text="No background polling · short-lived VISA sessions",
            style="Muted.TLabel",
        ).pack(side=tk.RIGHT, padx=(10, 0))

        # Main area: preview on the left, tabbed controls on the right.
        # This prevents low-priority buttons such as Settings from being pushed below
        # the visible screen area on smaller monitors.
        content = ttk.Frame(root)
        content.pack(fill=tk.BOTH, expand=True, pady=(16, 0))
        content.columnconfigure(0, weight=3)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        preview_area = ttk.Frame(content)
        preview_area.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        preview_area.rowconfigure(0, weight=1)
        preview_area.columnconfigure(0, weight=1)

        controls_area = ttk.Frame(content)
        controls_area.grid(row=0, column=1, sticky="nsew")
        controls_area.rowconfigure(0, weight=1)
        controls_area.columnconfigure(0, weight=1)

        self._build_image_preview(preview_area)
        self._build_control_tabs(controls_area)

        status = ttk.Label(root, textvariable=self.status_var, style="Status.TLabel", padding=(10, 6))
        status.pack(fill=tk.X, pady=(10, 0))

    def _build_control_tabs(self, parent: tk.Widget) -> None:
        """Build right-side tabs for connection, controls, settings, and log."""
        notebook = ttk.Notebook(parent)
        notebook.grid(row=0, column=0, sticky="nsew")

        connection_tab = ttk.Frame(notebook, padding=8)
        channels_tab = ttk.Frame(notebook, padding=8)
        trigger_tab = ttk.Frame(notebook, padding=8)
        settings_tab = ttk.Frame(notebook, padding=8)
        log_tab = ttk.Frame(notebook, padding=8)

        notebook.add(connection_tab, text="Connection")
        notebook.add(channels_tab, text="Channels")
        notebook.add(trigger_tab, text="Trigger")
        notebook.add(settings_tab, text="Settings")
        notebook.add(log_tab, text="Log")

        self._build_connection_card(connection_tab)
        self._build_channels_card(channels_tab)
        self._build_trigger_card(trigger_tab)
        self._build_settings_card(settings_tab)
        self._build_log(log_tab)

    def _card(self, parent: tk.Widget) -> ttk.Frame:
        return ttk.Frame(parent, style="Card.TFrame", padding=0)

    def _section_title(self, parent: tk.Widget, text: str) -> None:
        ttk.Label(parent, text=text, style="Section.TLabel").pack(anchor="w", padx=14, pady=(12, 4))

    def _build_connection_card(self, parent: tk.Widget) -> None:
        """Build connection controls as the first right-side tab."""
        card = self._card(parent)
        card.pack(fill=tk.X, pady=(0, 10))
        self._section_title(card, "Connection")

        # USB/VISA and Ethernet are both implemented as VISA resource strings.
        # Ethernet mode only helps the user generate the correct TCPIP resource.
        # Manual resource entry remains available as a backup method.
        mode_row = ttk.Frame(card, style="Card.TFrame")
        mode_row.pack(fill=tk.X, padx=14, pady=(8, 6))
        ttk.Label(mode_row, text="Mode", style="Card.TLabel").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(
            mode_row,
            text="USB / VISA",
            value="visa",
            variable=self.connection_mode_var,
            command=self._on_connection_mode_changed,
        ).pack(side=tk.LEFT, padx=(0, 16))
        ttk.Radiobutton(
            mode_row,
            text="Ethernet",
            value="ethernet",
            variable=self.connection_mode_var,
            command=self._on_connection_mode_changed,
        ).pack(side=tk.LEFT)

        visa_label_row = ttk.Frame(card, style="Card.TFrame")
        visa_label_row.pack(fill=tk.X, padx=14, pady=(6, 2))
        ttk.Label(visa_label_row, text="VISA resource", style="Card.TLabel").pack(side=tk.LEFT)

        visa_row = ttk.Frame(card, style="Card.TFrame")
        visa_row.pack(fill=tk.X, padx=14, pady=(0, 8))
        self.resource_combo = ttk.Combobox(
            visa_row,
            textvariable=self.resource_var,
            state="normal",
            values=(visaResourceAddr,),
        )
        self.resource_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
        ttk.Button(visa_row, text="Refresh", command=self.list_visa_resources).pack(side=tk.LEFT)

        eth_box = ttk.Frame(card, style="Card.TFrame")
        eth_box.pack(fill=tk.X, padx=14, pady=(6, 8))

        eth_host_row = ttk.Frame(eth_box, style="Card.TFrame")
        eth_host_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(eth_host_row, text="Ethernet IP/host", style="Card.TLabel").pack(side=tk.LEFT)
        ttk.Entry(eth_host_row, textvariable=self.eth_host_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))

        eth_protocol_row = ttk.Frame(eth_box, style="Card.TFrame")
        eth_protocol_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(eth_protocol_row, text="Protocol", style="Card.TLabel").pack(side=tk.LEFT)
        ttk.Combobox(
            eth_protocol_row,
            textvariable=self.eth_protocol_var,
            width=17,
            state="readonly",
            values=("VXI-11 / INSTR", "Raw SOCKET"),
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))

        eth_port_row = ttk.Frame(eth_box, style="Card.TFrame")
        eth_port_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(eth_port_row, text="Socket port", style="Card.TLabel").pack(side=tk.LEFT)
        ttk.Entry(eth_port_row, width=9, textvariable=self.eth_port_var).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(eth_port_row, text="Use Ethernet resource", command=self.apply_ethernet_resource).pack(
            side=tk.LEFT, padx=(8, 0)
        )

        generated_label_row = ttk.Frame(card, style="Card.TFrame")
        generated_label_row.pack(fill=tk.X, padx=14, pady=(6, 2))
        ttk.Label(generated_label_row, text="Generated Ethernet resource", style="Card.TLabel").pack(side=tk.LEFT)

        generated_row = ttk.Frame(card, style="Card.TFrame")
        generated_row.pack(fill=tk.X, padx=14, pady=(0, 8))
        ttk.Entry(generated_row, textvariable=self.generated_resource_var, state="readonly").pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )

        timeout_row = ttk.Frame(card, style="Card.TFrame")
        timeout_row.pack(fill=tk.X, padx=14, pady=(6, 8))
        ttk.Label(timeout_row, text="Timeout ms", style="Card.TLabel").pack(side=tk.LEFT)
        ttk.Entry(timeout_row, width=9, textvariable=self.timeout_var).pack(side=tk.LEFT, padx=(8, 0))

        button_row = ttk.Frame(card, style="Card.TFrame")
        button_row.pack(fill=tk.X, padx=14, pady=(0, 14))
        ttk.Button(button_row, text="Test IDN", style="Accent.TButton", command=self.test_connection).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )

        hint = ttk.Label(
            card,
            text="VXI-11: TCPIP0::<ip>::INSTR. Socket: TCPIP0::<ip>::4000::SOCKET.",
            style="Muted.TLabel",
            wraplength=360,
            justify=tk.LEFT,
        )
        hint.pack(fill=tk.X, padx=14, pady=(0, 14))

    def _build_channels_card(self, parent: tk.Widget) -> None:
        card = self._card(parent)
        card.pack(fill=tk.X, pady=(0, 10))
        self._section_title(card, "Channel labels")

        grid = ttk.Frame(card, style="Card.TFrame")
        grid.pack(fill=tk.X, padx=14, pady=(8, 12))

        for ch in range(1, 5):
            ttk.Label(grid, text=f"CH{ch}", style="Card.TLabel", width=5).grid(row=ch - 1, column=0, sticky="w", pady=4)
            ttk.Entry(grid, textvariable=self.label_vars[ch], width=30).grid(
                row=ch - 1, column=1, sticky="ew", padx=(8, 0), pady=4
            )
        grid.columnconfigure(1, weight=1)

        buttons = ttk.Frame(card, style="Card.TFrame")
        buttons.pack(fill=tk.X, padx=14, pady=(0, 14))
        ttk.Button(buttons, text="Read labels", command=self.read_labels).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Apply labels", style="Accent.TButton", command=self.apply_labels).pack(
            side=tk.LEFT, padx=(8, 0)
        )

    def _build_trigger_card(self, parent: tk.Widget) -> None:
        card = self._card(parent)
        card.pack(fill=tk.X, pady=(0, 10))
        self._section_title(card, "Trigger")

        body = ttk.Frame(card, style="Card.TFrame")
        body.pack(fill=tk.X, padx=14, pady=(8, 14))

        row = ttk.Frame(body, style="Card.TFrame")
        row.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(row, text="Source", style="Card.TLabel").pack(side=tk.LEFT)
        ttk.Combobox(
            row,
            textvariable=self.trigger_setup_channel_var,
            width=7,
            state="readonly",
            values=("1", "2", "3", "4"),
        ).pack(side=tk.LEFT, padx=(8, 14))

        ttk.Label(row, text="Level V", style="Card.TLabel").pack(side=tk.LEFT)
        ttk.Entry(row, textvariable=self.trigger_level_var, width=12).pack(side=tk.LEFT, padx=(8, 0), fill=tk.X, expand=True)

        ttk.Checkbutton(
            body,
            text="Set edge trigger source to selected channel",
            variable=self.trigger_set_source_var,
        ).pack(anchor="w", pady=(0, 8))

        readback_row = ttk.Frame(body, style="Card.TFrame")
        readback_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(readback_row, text="Readback", style="Card.TLabel").pack(side=tk.LEFT)
        ttk.Entry(readback_row, textvariable=self.trigger_readback_var, width=16, state="readonly").pack(
            side=tk.LEFT, padx=(8, 0), fill=tk.X, expand=True
        )

        buttons = ttk.Frame(body, style="Card.TFrame")
        buttons.pack(fill=tk.X)
        ttk.Button(buttons, text="Read trigger level", command=self.read_trigger_level).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(buttons, text="Set trigger level", style="Accent.TButton", command=self.apply_trigger_level).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0)
        )

    def _build_files_card(self, parent: tk.Widget) -> None:
        card = self._card(parent)
        card.pack(fill=tk.X, pady=(0, 10))
        self._section_title(card, "Image and CSV")

        body = ttk.Frame(card, style="Card.TFrame")
        body.pack(fill=tk.X, padx=14, pady=(8, 14))

        ttk.Checkbutton(
            body,
            text="Re-arm trigger after image capture",
            variable=self.rearm_after_image_var,
        ).pack(anchor="w", pady=(0, 8))

        image_row = ttk.Frame(body, style="Card.TFrame")
        image_row.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(image_row, text="Trigger channel after image", style="Card.TLabel").pack(side=tk.LEFT)
        trig_combo = ttk.Combobox(
            image_row,
            textvariable=self.trigger_channel_var,
            width=7,
            state="readonly",
            values=("", "1", "2", "3", "4"),
        )
        trig_combo.pack(side=tk.LEFT, padx=(8, 0))

        ttk.Button(body, text="Capture preview", command=self.capture_preview).pack(fill=tk.X, pady=3)
        ttk.Button(body, text="Save PNG image...", command=self.save_png_image).pack(fill=tk.X, pady=3)
        ttk.Button(body, text="Save enabled channels to CSV...", style="Accent.TButton", command=self.save_csv).pack(
            fill=tk.X, pady=3
        )

    def _build_settings_card(self, parent: tk.Widget) -> None:
        card = self._card(parent)
        card.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self._section_title(card, "Output and scope settings")

        body = ttk.Frame(card, style="Card.TFrame")
        body.pack(fill=tk.BOTH, expand=True, padx=14, pady=(8, 14))

        folder_row = ttk.Frame(body, style="Card.TFrame")
        folder_row.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(folder_row, text="Destination folder", style="Card.TLabel").pack(anchor="w")

        folder_pick_row = ttk.Frame(body, style="Card.TFrame")
        folder_pick_row.pack(fill=tk.X, pady=(0, 12))
        ttk.Entry(folder_pick_row, textvariable=self.output_folder_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(folder_pick_row, text="Pick folder", command=self.pick_output_folder).pack(side=tk.LEFT, padx=(8, 0))

        ttk.Label(
            body,
            text="Filename format: <prefix><base><_timestamp optional>.<extension>",
            style="Muted.TLabel",
            wraplength=360,
            justify=tk.LEFT,
        ).pack(fill=tk.X, pady=(0, 10))

        self._build_naming_row(
            body,
            title="PNG images",
            prefix_var=self.png_prefix_var,
            base_var=self.png_base_var,
            timestamp_var=self.png_add_timestamp_var,
        )
        self._build_naming_row(
            body,
            title="CSV waveforms",
            prefix_var=self.csv_prefix_var,
            base_var=self.csv_base_var,
            timestamp_var=self.csv_add_timestamp_var,
        )
        self._build_naming_row(
            body,
            title="Settings JSON",
            prefix_var=self.settings_prefix_var,
            base_var=self.settings_base_var,
            timestamp_var=self.settings_add_timestamp_var,
        )

        ttk.Separator(body).pack(fill=tk.X, pady=(8, 10))

        ttk.Checkbutton(
            body,
            text="Wait for *OPC? after restore (can timeout on DPO4000)",
            variable=self.restore_wait_opc_var,
        ).pack(anchor="w", pady=(0, 8))

        ttk.Button(body, text="Save settings JSON", command=self.save_settings).pack(fill=tk.X, pady=3)
        ttk.Button(body, text="Restore settings JSON...", style="Accent.TButton", command=self.restore_settings).pack(
            fill=tk.X, pady=3
        )

    def _build_naming_row(
        self,
        parent: tk.Widget,
        title: str,
        prefix_var: tk.StringVar,
        base_var: tk.StringVar,
        timestamp_var: tk.BooleanVar,
    ) -> None:
        """Build one compact filename-options row in the Settings tab."""
        box = ttk.Frame(parent, style="Card.TFrame")
        box.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(box, text=title, style="Card.TLabel").pack(anchor="w", pady=(0, 4))

        row = ttk.Frame(box, style="Card.TFrame")
        row.pack(fill=tk.X)

        ttk.Label(row, text="Prefix", style="Card.TLabel").pack(side=tk.LEFT)
        ttk.Entry(row, width=9, textvariable=prefix_var).pack(side=tk.LEFT, padx=(6, 10))

        ttk.Label(row, text="Base", style="Card.TLabel").pack(side=tk.LEFT)
        ttk.Entry(row, width=13, textvariable=base_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 10))

        ttk.Checkbutton(row, text="Timestamp", variable=timestamp_var).pack(side=tk.LEFT)

    def _build_image_preview(self, parent: tk.Widget) -> None:
        card = self._card(parent)
        card.grid(row=0, column=0, sticky="nsew")

        # IMPORTANT: _section_title() uses pack() inside this card, so every
        # other child of the same card must also use pack(). Tkinter does not
        # allow mixing pack() and grid() in one parent container.
        self._section_title(card, "Screen preview")

        self.preview_label = ttk.Label(
            card,
            text="Press 'Capture preview' to read the current scope screen.",
            style="Card.TLabel",
            anchor="center",
        )
        # The preview expands, while the Image/CSV action panel below remains
        # pinned to the bottom of the preview card.
        self.preview_label.pack(fill=tk.BOTH, expand=True, padx=14, pady=(8, 8))
        self.preview_label.bind("<Configure>", self._on_preview_resize)

        self._build_preview_bottom_actions(card)

    def _build_preview_bottom_actions(self, parent: tk.Widget) -> None:
        """Build Image/CSV controls directly below the screen preview."""
        action_bar = ttk.Frame(parent, style="Card.TFrame")
        action_bar.pack(fill=tk.X, padx=14, pady=(0, 14))

        options_row = ttk.Frame(action_bar, style="Card.TFrame")
        options_row.pack(fill=tk.X, pady=(0, 8))

        ttk.Checkbutton(
            options_row,
            text="Re-arm trigger after image capture",
            variable=self.rearm_after_image_var,
        ).pack(side=tk.LEFT)

        ttk.Label(options_row, text="Trigger channel", style="Card.TLabel").pack(side=tk.LEFT, padx=(18, 8))
        ttk.Combobox(
            options_row,
            textvariable=self.trigger_channel_var,
            width=7,
            state="readonly",
            values=("", "1", "2", "3", "4"),
        ).pack(side=tk.LEFT)

        buttons_row = ttk.Frame(action_bar, style="Card.TFrame")
        buttons_row.pack(fill=tk.X)

        ttk.Button(buttons_row, text="Capture preview", command=self.capture_preview).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )
        ttk.Button(buttons_row, text="Save PNG image...", command=self.save_png_image).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0)
        )
        ttk.Button(
            buttons_row,
            text="Save enabled channels to CSV...",
            style="Accent.TButton",
            command=self.save_csv,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))

    def _build_log(self, parent: tk.Widget) -> None:
        log_card = self._card(parent)
        log_card.pack(fill=tk.BOTH, expand=True, pady=(0, 0))
        self._section_title(log_card, "Log")
        self.log_text = tk.Text(
            log_card,
            height=7,
            bg="#020617",
            fg="#d1d5db",
            insertbackground="#ffffff",
            relief=tk.FLAT,
            wrap=tk.WORD,
            font=("Consolas", 9),
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=14, pady=(8, 14))
        self.log_text.configure(state=tk.DISABLED)

    # ---------------------------------------------------------------------
    # General helpers
    # ---------------------------------------------------------------------
    def _append_log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _set_busy(self, busy: bool, status: str | None = None) -> None:
        self._busy = busy
        if status:
            self.status_var.set(status)
        cursor = "watch" if busy else ""
        self.configure(cursor=cursor)

    def _poll_result_queue(self) -> None:
        try:
            while True:
                result = self._result_queue.get_nowait()
                self._set_busy(False)
                if result.ok:
                    self.status_var.set(result.message)
                    self._append_log(result.message)
                    if isinstance(result.payload, dict) and result.payload.get("preview_path"):
                        self._load_preview(Path(result.payload["preview_path"]))
                    if isinstance(result.payload, dict) and result.payload.get("labels"):
                        for ch, label in result.payload["labels"].items():
                            self.label_vars[int(ch)].set(label)
                    if isinstance(result.payload, dict) and "visa_resources" in result.payload:
                        self._update_visa_resource_list(result.payload["visa_resources"])
                    if isinstance(result.payload, dict) and "trigger_level" in result.payload:
                        self.trigger_readback_var.set(str(result.payload["trigger_level"]))
                else:
                    self.status_var.set("Error")
                    self._append_log(f"ERROR: {result.message}")
                    messagebox.showerror(APP_TITLE, result.message)
        except queue.Empty:
            pass
        self.after(100, self._poll_result_queue)

    def _run_job(self, description: str, func) -> None:
        if self._busy:
            messagebox.showinfo(APP_TITLE, "Another scope operation is already running.")
            return

        self._set_busy(True, description)
        self._append_log(description)

        def worker() -> None:
            try:
                payload = func()
                self._result_queue.put(JobResult(True, f"Done: {description}", payload))
            except Exception as exc:
                self._result_queue.put(JobResult(False, str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _require_driver(self) -> None:
        if DPO4054 is None:
            raise RuntimeError(
                "Could not import DPO4054 from tektronix_utils.py. "
                "Place this GUI file in the same folder as tektronix_utils.py. "
                f"Original error: {DRIVER_IMPORT_ERROR}"
            )

    def _on_connection_mode_changed(self) -> None:
        """Update resource field when the user switches connection mode."""
        if self.connection_mode_var.get() == "ethernet":
            try:
                self.apply_ethernet_resource(show_message=False)
            except Exception:
                # User may not have entered an IP address yet. Keep quiet here.
                pass

    def _ethernet_resource_name(self) -> str:
        """Build a VISA TCPIP resource string from the Ethernet fields."""
        host = self.eth_host_var.get().strip()
        if not host:
            raise ValueError("Ethernet IP/host cannot be empty.")

        protocol = self.eth_protocol_var.get().strip()
        if protocol == "Raw SOCKET":
            try:
                port = int(self.eth_port_var.get().strip())
            except ValueError as exc:
                raise ValueError("Ethernet socket port must be an integer.") from exc
            if port < 1 or port > 65535:
                raise ValueError("Ethernet socket port must be between 1 and 65535.")
            return f"TCPIP0::{host}::{port}::SOCKET"

        # VXI-11 / INSTR. On Tektronix LAN scopes this is usually the most
        # compatible VISA form when NI-VISA/TekVISA/Keysight VISA is installed.
        return f"TCPIP0::{host}::INSTR"

    def _selected_resource_name(self) -> str:
        """Return the resource that should be used for the next operation."""
        if self.connection_mode_var.get() == "ethernet":
            resource = self._ethernet_resource_name()
            self.generated_resource_var.set(resource)
            return resource

        resource = self.resource_var.get().strip()
        if not resource:
            raise ValueError("VISA resource cannot be empty.")
        return resource

    def apply_ethernet_resource(self, show_message: bool = True) -> None:
        """Generate Ethernet VISA string and copy it into the main resource field."""
        resource = self._ethernet_resource_name()
        self.generated_resource_var.set(resource)
        self.resource_var.set(resource)
        self.connection_mode_var.set("ethernet")
        values = list(self.resource_combo.cget("values"))
        if resource not in values:
            values.insert(0, resource)
            self.resource_combo.configure(values=tuple(values))
        if show_message:
            self._append_log(f"Ethernet resource selected: {resource}")
            self.status_var.set(f"Ethernet resource selected: {resource}")

    def _update_visa_resource_list(self, resources) -> None:
        """
        Update the editable VISA resource dropdown.

        The combobox remains editable, so a manually typed VISA address is still
        valid even if it is not returned by list_resources().
        """
        resources = tuple(str(item) for item in resources)
        current = self.resource_var.get().strip()

        values = list(resources)
        if current and current not in values:
            values.insert(0, current)
        if visaResourceAddr and visaResourceAddr not in values:
            values.append(visaResourceAddr)

        self.resource_combo.configure(values=tuple(values))

        # If current field is empty and resources were found, select the first one.
        if not current and resources:
            self.resource_var.set(resources[0])

    def _timeout_ms(self) -> int:
        try:
            timeout = int(self.timeout_var.get())
        except ValueError as exc:
            raise ValueError("Timeout must be an integer number of milliseconds.") from exc
        if timeout < 1000:
            raise ValueError("Timeout should be at least 1000 ms.")
        return timeout

    def pick_output_folder(self) -> None:
        """Let user select the folder used for PNG, CSV, and settings JSON files."""
        try:
            initial_dir = str(self._configured_output_folder(create=False))
        except Exception:
            initial_dir = str(Path.cwd())

        selected = filedialog.askdirectory(
            title="Select output folder for PNG, CSV, and scope settings",
            initialdir=initial_dir,
        )
        if selected:
            self.output_folder_var.set(selected)
            folder = self._configured_output_folder(create=True)
            self._append_log(f"Output folder set to: {folder}")
            self.status_var.set(f"Output folder set to: {folder}")

    def _configured_output_folder(self, create: bool = True) -> Path:
        """Return the configured output folder as an absolute Path."""
        raw = self.output_folder_var.get().strip()
        folder = Path(raw).expanduser() if raw else Path.cwd() / "scope_gui_output"
        if not folder.is_absolute():
            folder = Path.cwd() / folder
        if create:
            folder.mkdir(parents=True, exist_ok=True)
        self.output_folder = folder
        return folder

    @staticmethod
    def _safe_filename_part(text: str, fallback: str) -> str:
        """Return a filesystem-safe filename part for Windows/Linux."""
        text = (text or "").strip()
        if not text:
            text = fallback
        invalid = '<>:"/\\|?*'
        cleaned = ''.join('_' if ch in invalid or ord(ch) < 32 else ch for ch in text)
        cleaned = cleaned.strip(" ._")
        return cleaned or fallback

    def _build_output_path(self, kind: str) -> Path:
        """Build output filename from Settings tab options."""
        if kind == "png":
            prefix = self.png_prefix_var.get()
            base = self.png_base_var.get()
            add_timestamp = self.png_add_timestamp_var.get()
            extension = ".png"
            fallback = "scope_screen"
        elif kind == "csv":
            prefix = self.csv_prefix_var.get()
            base = self.csv_base_var.get()
            add_timestamp = self.csv_add_timestamp_var.get()
            extension = ".csv"
            fallback = "scope_waveform"
        elif kind == "settings":
            prefix = self.settings_prefix_var.get()
            base = self.settings_base_var.get()
            add_timestamp = self.settings_add_timestamp_var.get()
            extension = ".json"
            fallback = "dpo4054_setup"
        else:
            raise ValueError(f"Unknown output kind: {kind}")

        prefix = self._safe_filename_part(prefix, "") if prefix.strip() else ""
        base = self._safe_filename_part(base, fallback)

        name = f"{prefix}{base}"
        if add_timestamp:
            name += "_" + datetime.now().strftime("%Y%m%d_%H%M%S")
        return self._configured_output_folder(create=True) / f"{name}{extension}"

    def _confirm_or_cancel_overwrite(self, path: Path) -> bool:
        """Ask before overwriting a file, mainly for timestamp-disabled saves."""
        if not path.exists():
            return True
        return messagebox.askyesno(
            APP_TITLE,
            f"File already exists:\n{path}\n\nOverwrite it?",
        )

    def _new_scope_session(self, action):
        """
        Open a short-lived DPO4054 session, run action(scope), then close it.

        This is the key design choice that avoids blocking the USB/VISA scope
        session while the GUI is idle.
        """
        self._require_driver()
        resource_name = self._selected_resource_name()
        scope = DPO4054(resource_name, auto_connect=False)
        try:
            scope.connect()
            if getattr(scope, "scope", None) is not None:
                scope.scope.timeout = self._timeout_ms()
                # Raw TCP socket VISA sessions generally need explicit line
                # termination for SCPI query/write operations. USBTMC/VXI-11
                # sessions tolerate this setting in normal use.
                try:
                    scope.scope.write_termination = "\n"
                    scope.scope.read_termination = "\n"
                except Exception:
                    pass
            return action(scope)
        finally:
            try:
                scope.disconnect()
            except Exception:
                pass

    @staticmethod
    def _safe_label_text(text: str) -> str:
        # Tek labels are short quoted strings. Avoid breaking the SCPI quote.
        return text.replace('"', "'")[:30]

    def _trigger_channel_or_none(self) -> int | None:
        value = self.trigger_channel_var.get().strip()
        if not value:
            return None
        return int(value)

    def _selected_trigger_channel(self) -> int:
        value = self.trigger_setup_channel_var.get().strip()
        if value not in {"1", "2", "3", "4"}:
            raise ValueError("Trigger source channel must be 1, 2, 3, or 4.")
        return int(value)

    def _parsed_trigger_level(self):
        value = self.trigger_level_var.get().strip()
        if not value:
            raise ValueError("Trigger level cannot be empty.")

        # Tektronix accepts numeric volts and presets such as TTL/ECL.
        preset = value.upper()
        if preset in {"TTL", "ECL"}:
            return preset

        try:
            return float(value)
        except ValueError as exc:
            raise ValueError("Trigger level must be a number in volts, or TTL/ECL.") from exc

    def _on_preview_resize(self, _event=None) -> None:
        """Re-render the preview image after the preview panel is resized."""
        if self._last_image_path is None:
            return

        # Debounce resize events. Windows can generate many while resizing.
        if self._preview_resize_job is not None:
            try:
                self.after_cancel(self._preview_resize_job)
            except Exception:
                pass

        self._preview_resize_job = self.after(120, lambda: self._render_preview_to_fit(self._last_image_path))

    def _load_preview(self, path: Path) -> None:
        self._last_image_path = path
        self._render_preview_to_fit(path)

    def _preview_area_size(self) -> tuple[int, int]:
        """Return useful preview area size in pixels."""
        width = self.preview_label.winfo_width()
        height = self.preview_label.winfo_height()

        # During first rendering Tk may not have calculated widget size yet.
        if width <= 10 or height <= 10:
            self.update_idletasks()
            width = self.preview_label.winfo_width()
            height = self.preview_label.winfo_height()

        # Fallback values for very early startup or minimized window.
        width = width if width > 10 else 820
        height = height if height > 10 else 500

        # Keep small inner margin so image does not touch card border.
        return max(120, width - 12), max(90, height - 12)

    def _render_preview_to_fit(self, path: Path) -> None:
        """Load preview image and scale it to fit the current preview panel."""
        try:
            max_w, max_h = self._preview_area_size()

            if Image is not None and ImageTk is not None:
                # Best quality path if Pillow is installed.
                with Image.open(path) as source:
                    source.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
                    img = ImageTk.PhotoImage(source.copy())
            else:
                # Dependency-free fallback. Tk PhotoImage supports integer-only
                # subsampling, so use ceil() to guarantee the image always fits.
                img = tk.PhotoImage(file=str(path))
                scale = max(img.width() / max_w, img.height() / max_h, 1)
                factor = max(1, math.ceil(scale))
                if factor > 1:
                    img = img.subsample(factor, factor)

            self._preview_image = img
            self.preview_label.configure(image=img, text="")
        except Exception as exc:
            self.preview_label.configure(
                image="",
                text=f"Image saved, but preview could not be loaded:\n{path}\n\n{exc}",
            )

    # ---------------------------------------------------------------------
    # GUI actions
    # ---------------------------------------------------------------------
    def test_connection(self) -> None:
        def job():
            def action(scope):
                return {"idn": scope.scope.query("*IDN?").strip()}

            result = self._new_scope_session(action)
            return {"labels": {}, "idn": result["idn"]}

        self._run_job("Testing scope connection", job)

    def list_visa_resources(self) -> None:
        def job():
            if pyvisa is None:
                raise RuntimeError("pyvisa is not installed.")

            rm = pyvisa.ResourceManager()
            try:
                resources = tuple(rm.list_resources())
            finally:
                rm.close()

            if resources:
                self.after(
                    0,
                    lambda: messagebox.showinfo(
                        APP_TITLE,
                        "VISA resources found:\n" + "\n".join(resources),
                    ),
                )
            else:
                self.after(0, lambda: messagebox.showinfo(APP_TITLE, "No VISA resources found."))

            return {"visa_resources": resources}

        self._run_job("Refreshing VISA resource list", job)

    def read_labels(self) -> None:
        def job():
            def action(scope):
                return {ch: scope.get_channel_label(ch) for ch in range(1, 5)}

            labels = self._new_scope_session(action)
            return {"labels": labels}

        self._run_job("Reading CH1..CH4 labels", job)

    def apply_labels(self) -> None:
        labels = {ch: self._safe_label_text(var.get()) for ch, var in self.label_vars.items()}

        def job():
            def action(scope):
                for ch, label in labels.items():
                    scope.set_channel_label(ch, label)
                return {ch: scope.get_channel_label(ch) for ch in range(1, 5)}

            readback = self._new_scope_session(action)
            return {"labels": readback}

        self._run_job("Applying CH1..CH4 labels", job)

    def read_trigger_level(self) -> None:
        channel = self._selected_trigger_channel()

        def job():
            def action(scope):
                if hasattr(scope, "get_trigger_level"):
                    return scope.get_trigger_level(channel=channel)
                response = scope.scope.query(f"TRIGGER:A:LEVEL:CH{channel}?").strip()
                return float(response.split()[-1])

            level = self._new_scope_session(action)
            return {"trigger_level": level}

        self._run_job(f"Reading trigger level for CH{channel}", job)

    def apply_trigger_level(self) -> None:
        channel = self._selected_trigger_channel()
        level = self._parsed_trigger_level()
        set_source = self.trigger_set_source_var.get()

        def job():
            def action(scope):
                if set_source:
                    if hasattr(scope, "set_edge_trigger_source"):
                        scope.set_edge_trigger_source(channel)
                    else:
                        scope.scope.write(f"TRIGGER:A:EDGE:SOURCE CH{channel}")

                if hasattr(scope, "set_trigger_level"):
                    readback = scope.set_trigger_level(level, channel=channel, verify=True)
                else:
                    scope.scope.write(f"TRIGGER:A:LEVEL:CH{channel} {level}")
                    response = scope.scope.query(f"TRIGGER:A:LEVEL:CH{channel}?").strip()
                    readback = float(response.split()[-1])

                # Keep acquisition running/re-armed after trigger changes.
                try:
                    scope.scope.write("ACQUIRE:STATE RUN")
                except Exception:
                    pass
                return readback

            readback = self._new_scope_session(action)
            return {"trigger_level": readback}

        self._run_job(f"Setting trigger CH{channel} level to {level}", job)

    def capture_preview(self) -> None:
        path = self._build_output_path("png")
        if not self._confirm_or_cancel_overwrite(path):
            return
        self._capture_image_to(path, description="Capturing scope image preview")

    def save_png_image(self) -> None:
        path = self._build_output_path("png")
        if not self._confirm_or_cancel_overwrite(path):
            return
        self._capture_image_to(path, description="Saving scope PNG image")

    def _capture_image_to(self, path: Path, description: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        rearm = self.rearm_after_image_var.get()
        trigger_channel = self._trigger_channel_or_none()

        def job():
            def action(scope):
                # Do not use the base driver's save_image_path() here because it
                # writes whatever read_raw() returns directly to disk. On some
                # DPO4000 VISA backends, especially Ethernet/SOCKET, the response
                # may include a SCPI definite-length block header or a short text
                # prefix before the actual PNG stream. That produces a file that
                # Pillow/Tk cannot identify as an image. This GUI path extracts and
                # validates the image payload before saving.
                saved_path = self._save_scope_image_png_robust(scope, path)
                if rearm and hasattr(scope, "rearm_trigger_after_image"):
                    scope.rearm_trigger_after_image(trigger_channel=trigger_channel)
                return str(saved_path)

            saved = self._new_scope_session(action)
            return {"preview_path": saved}

        self._run_job(description, job)

    @staticmethod
    def _save_scope_image_png_robust(scope, path: Path) -> Path:
        """
        Capture the oscilloscope display and save a clean PNG file.

        Tektronix DPO4000 hardcopy transfer can return either a raw PNG stream
        or a SCPI binary block that contains the PNG. Some VISA backends can also
        leave a text prefix before the PNG bytes. This method normalizes the
        response before writing the file so the GUI preview can open it reliably.
        """
        inst = scope.scope
        if inst is None:
            raise ConnectionError("Oscilloscope is not connected.")

        old_timeout = getattr(inst, "timeout", None)
        old_read_termination = getattr(inst, "read_termination", None)
        old_write_termination = getattr(inst, "write_termination", None)

        try:
            # Image transfers can be slower over LAN than USB.
            try:
                inst.timeout = max(int(old_timeout or 0), 60_000)
            except Exception:
                pass

            # Binary transfers must not be cut at newline characters.
            try:
                inst.read_termination = None
            except Exception:
                pass
            try:
                inst.write_termination = "\n"
            except Exception:
                pass

            # Keep commands compatible with DPO4000 generation. Some models accept
            # HARDCOPY:FORMAT, while the uploaded base utility already uses
            # SAVE:IMAGE:FILEFORMAT. Send both and ignore unsupported variants.
            for command in (
                "*CLS",
                "HEADER OFF",
                "VERBOSE OFF",
                "HARDCOPY:FORMAT PNG",
                "SAVE:IMAGE:FILEFORMAT PNG",
                "SAVE:IMAGE:INKSAVER OFF",
            ):
                try:
                    inst.write(command)
                    time.sleep(0.03)
                except Exception:
                    pass

            # Request hardcopy data. The short form used in the base driver is
            # accepted by DPO4000 scopes; the long form is attempted if needed.
            try:
                inst.write("HARDCOPY START")
            except Exception:
                inst.write("HARDCOPY:START")

            raw = inst.read_raw()
            png_data = ScopeGui._extract_png_payload(raw)

            if not png_data.startswith(b"\x89PNG\r\n\x1a\n"):
                raise RuntimeError("Scope did not return PNG image data.")

            # Trim trailing VISA padding/status bytes after the PNG IEND chunk.
            png_data = ScopeGui._trim_png_after_iend(png_data)

            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(png_data)
            return path
        finally:
            # Restore VISA session settings before the short-lived session closes.
            try:
                if old_timeout is not None:
                    inst.timeout = old_timeout
            except Exception:
                pass
            try:
                inst.read_termination = old_read_termination
            except Exception:
                pass
            try:
                inst.write_termination = old_write_termination
            except Exception:
                pass

    @staticmethod
    def _extract_png_payload(raw: bytes) -> bytes:
        """Extract a PNG stream from raw VISA hardcopy bytes."""
        if not raw:
            raise RuntimeError("Scope returned empty image data.")

        data = bytes(raw)

        # Case 1: IEEE/SCPI definite-length binary block: #<digits><length><data>
        # Example: #9001234567<PNG bytes>
        if data.startswith(b"#") and len(data) >= 3 and data[1:2].isdigit():
            ndigits = int(chr(data[1]))
            length_start = 2
            length_end = length_start + ndigits
            if len(data) >= length_end:
                try:
                    payload_len = int(data[length_start:length_end].decode("ascii"))
                    payload_start = length_end
                    payload_end = payload_start + payload_len
                    if len(data) >= payload_start:
                        data = data[payload_start:payload_end]
                except Exception:
                    # Fall through to signature search below.
                    pass

        # Case 2: raw PNG starts after a text prefix or backend-specific bytes.
        png_signature = b"\x89PNG\r\n\x1a\n"
        png_index = data.find(png_signature)
        if png_index >= 0:
            return data[png_index:]

        # Report useful diagnostic information instead of only "can't identify image".
        prefix = data[:120].replace(b"\r", b"\\r").replace(b"\n", b"\\n")
        try:
            prefix_text = prefix.decode("ascii", errors="replace")
        except Exception:
            prefix_text = repr(prefix)
        raise RuntimeError(
            "No PNG signature found in scope hardcopy response. "
            f"First bytes: {prefix_text!r}. "
            "Try USB/VXI-11 first; for raw SOCKET check port and VISA backend."
        )

    @staticmethod
    def _trim_png_after_iend(data: bytes) -> bytes:
        """Return data through the PNG IEND chunk, leaving valid PNG bytes only."""
        # PNG chunk layout around IEND:
        #   4-byte length, 4-byte type 'IEND', 4-byte CRC
        # data.find(b'IEND') returns the chunk-type offset, so include type+CRC.
        iend_index = data.find(b"IEND")
        if iend_index >= 0 and len(data) >= iend_index + 8:
            return data[: iend_index + 8]
        return data

    def save_csv(self) -> None:
        path = self._build_output_path("csv")
        if not self._confirm_or_cancel_overwrite(path):
            return
        path.parent.mkdir(parents=True, exist_ok=True)

        def job():
            def action(scope):
                scope.save_all_channels_to_single_csv(str(path))
                return str(path)

            saved = self._new_scope_session(action)
            return {"saved_path": saved}

        self._run_job("Saving enabled channel waveforms to CSV", job)

    def save_settings(self) -> None:
        path = self._build_output_path("settings")
        if not self._confirm_or_cancel_overwrite(path):
            return
        path.parent.mkdir(parents=True, exist_ok=True)

        def job():
            def action(scope):
                # File dialog already handles overwrite confirmation; avoid console input in GUI.
                saved = scope.save_scope_settings(str(path), ask_before_overwrite=False)
                return str(saved)

            saved = self._new_scope_session(action)
            return {"saved_path": saved}

        self._run_job("Saving scope settings JSON", job)

    def restore_settings(self) -> None:
        selected = filedialog.askopenfilename(
            title="Restore scope settings JSON",
            initialdir=str(self._configured_output_folder(create=True)),
            filetypes=[("JSON file", "*.json"), ("All files", "*.*")],
        )
        if not selected:
            return
        path = Path(selected)
        wait_opc = self.restore_wait_opc_var.get()

        def job():
            def action(scope):
                if hasattr(scope, "apply_scope_settings"):
                    return scope.apply_scope_settings(
                        str(path),
                        wait_complete=wait_opc,
                        check_error=True,
                        opc_timeout_ms=DEFAULT_RESTORE_TIMEOUT_MS,
                    )
                return self._apply_scope_settings_locally(scope, path, wait_complete=wait_opc)

            data = self._new_scope_session(action)
            instrument = data.get("instrument", "Unknown") if isinstance(data, dict) else "Unknown"
            return {"instrument": instrument}

        self._run_job("Restoring scope settings JSON", job)

    @staticmethod
    def _apply_scope_settings_locally(
        scope,
        file_path: Path,
        wait_complete: bool = False,
        check_error: bool = True,
        restore_delay_s: float = 2.0,
        opc_timeout_ms: int = DEFAULT_RESTORE_TIMEOUT_MS,
    ) -> dict:
        """
        Restore scope settings from a JSON file created by save_scope_settings().

        This exists because the uploaded base driver has apply_scope_settings()
        commented out. Keeping restore logic here avoids changing the base driver.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Scope setup file not found: {file_path}")

        data = json.loads(file_path.read_text(encoding="utf-8"))
        setup_string = data.get("setup")
        if not setup_string:
            raise ValueError("Invalid setup file: missing or empty 'setup' field.")

        scope.scope.write("*CLS")
        scope.scope.write(setup_string)
        time.sleep(restore_delay_s)

        if wait_complete:
            old_timeout = scope.scope.timeout
            try:
                scope.scope.timeout = opc_timeout_ms
                scope.scope.query("*OPC?")
            except VisaIOError as exc:
                raise TimeoutError(
                    "Timeout while waiting for *OPC? after restoring settings. "
                    "The setup may still have been applied. Disable the *OPC? checkbox "
                    "or increase the timeout."
                ) from exc
            finally:
                scope.scope.timeout = old_timeout

        if check_error:
            try:
                esr_text = scope.scope.query("*ESR?").strip()
                esr = int(esr_text)
            except Exception as exc:
                raise RuntimeError("Could not read *ESR? after applying settings.") from exc

            if esr != 0:
                try:
                    error_text = scope.scope.query("ALLEV?").strip()
                except Exception:
                    error_text = "Could not read ALLEV?"
                raise RuntimeError(f"Scope reported error after restore. ESR={esr}, ALLEV={error_text}")

        return data


if __name__ == "__main__":
    app = ScopeGui()
    app.mainloop()
