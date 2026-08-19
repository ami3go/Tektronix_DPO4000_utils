"""
Modern Tkinter GUI for Tektronix DPO4054 / DPO4000 scopes.

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
    python tektronix_scope_gui.py
"""

from __future__ import annotations

import json
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
        self.geometry("1120x760")
        self.minsize(980, 680)

        self.output_folder = Path.cwd() / "scope_gui_output"
        self.output_folder.mkdir(parents=True, exist_ok=True)

        self._result_queue: queue.Queue[JobResult] = queue.Queue()
        self._busy = False
        self._preview_image: tk.PhotoImage | None = None
        self._last_image_path: Path | None = None

        self._build_style()
        self._build_variables()
        self._build_layout()
        self._poll_result_queue()

        if DRIVER_IMPORT_ERROR is not None:
            self._append_log(
                "Driver import problem. Put tektronix_scope_gui.py next to tektronix_utils.py.\n"
                f"Import error: {DRIVER_IMPORT_ERROR}"
            )

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

    def _build_variables(self) -> None:
        self.resource_var = tk.StringVar(value=visaResourceAddr)
        self.timeout_var = tk.StringVar(value=str(DEFAULT_TIMEOUT_MS))
        self.trigger_channel_var = tk.StringVar(value="")
        self.restore_wait_opc_var = tk.BooleanVar(value=False)
        self.rearm_after_image_var = tk.BooleanVar(value=True)
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

        resource_card = self._card(root)
        resource_card.pack(fill=tk.X, pady=(16, 10))
        self._section_title(resource_card, "Connection")

        res_row = ttk.Frame(resource_card, style="Card.TFrame")
        res_row.pack(fill=tk.X, padx=14, pady=(8, 14))
        ttk.Label(res_row, text="VISA resource", style="Card.TLabel").pack(side=tk.LEFT, padx=(0, 8))

        # Editable combobox: user can pick from discovered VISA resources OR type/paste
        # the resource manually as a backup method.
        self.resource_combo = ttk.Combobox(
            res_row,
            textvariable=self.resource_var,
            state="normal",
            values=(visaResourceAddr,),
        )
        self.resource_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))

        ttk.Label(res_row, text="Timeout ms", style="Card.TLabel").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Entry(res_row, width=9, textvariable=self.timeout_var).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(res_row, text="Refresh VISA list", command=self.list_visa_resources).pack(side=tk.LEFT)
        ttk.Button(res_row, text="Test IDN", style="Accent.TButton", command=self.test_connection).pack(side=tk.LEFT, padx=(8, 0))

        content = ttk.Frame(root)
        content.pack(fill=tk.BOTH, expand=True)
        content.columnconfigure(0, weight=0)
        content.columnconfigure(1, weight=1)
        content.rowconfigure(0, weight=1)

        left = ttk.Frame(content)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

        right = ttk.Frame(content)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        self._build_channels_card(left)
        self._build_files_card(left)
        self._build_settings_card(left)
        self._build_image_preview(right)
        self._build_log(root)

        status = ttk.Label(root, textvariable=self.status_var, style="Status.TLabel", padding=(10, 6))
        status.pack(fill=tk.X, pady=(10, 0))

    def _card(self, parent: tk.Widget) -> ttk.Frame:
        return ttk.Frame(parent, style="Card.TFrame", padding=0)

    def _section_title(self, parent: tk.Widget, text: str) -> None:
        ttk.Label(parent, text=text, style="Section.TLabel").pack(anchor="w", padx=14, pady=(12, 4))

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
        card.pack(fill=tk.X, pady=(0, 10))
        self._section_title(card, "Scope settings")

        body = ttk.Frame(card, style="Card.TFrame")
        body.pack(fill=tk.X, padx=14, pady=(8, 14))

        ttk.Checkbutton(
            body,
            text="Wait for *OPC? after restore (can timeout on DPO4000)",
            variable=self.restore_wait_opc_var,
        ).pack(anchor="w", pady=(0, 8))

        ttk.Button(body, text="Save settings JSON...", command=self.save_settings).pack(fill=tk.X, pady=3)
        ttk.Button(body, text="Restore settings JSON...", style="Accent.TButton", command=self.restore_settings).pack(
            fill=tk.X, pady=3
        )

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
        self.preview_label.pack(fill=tk.BOTH, expand=True, padx=14, pady=(8, 14))

    def _build_log(self, parent: tk.Widget) -> None:
        log_card = self._card(parent)
        log_card.pack(fill=tk.BOTH, expand=False, pady=(10, 0))
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

    def _new_scope_session(self, action):
        """
        Open a short-lived DPO4054 session, run action(scope), then close it.

        This is the key design choice that avoids blocking the USB/VISA scope
        session while the GUI is idle.
        """
        self._require_driver()
        scope = DPO4054(self.resource_var.get().strip(), auto_connect=False)
        try:
            scope.connect()
            if getattr(scope, "scope", None) is not None:
                scope.scope.timeout = self._timeout_ms()
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

    def _load_preview(self, path: Path) -> None:
        self._last_image_path = path
        try:
            img = tk.PhotoImage(file=str(path))
            max_w, max_h = 860, 520
            factor = max(1, int(max(img.width() / max_w, img.height() / max_h)))
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

    def capture_preview(self) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.output_folder / f"scope_screen_{timestamp}.png"
        self._capture_image_to(path, description="Capturing scope image preview")

    def save_png_image(self) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"scope_screen_{timestamp}.png"
        selected = filedialog.asksaveasfilename(
            title="Save scope screen image",
            initialdir=str(self.output_folder),
            initialfile=default_name,
            defaultextension=".png",
            filetypes=[("PNG image", "*.png"), ("All files", "*.*")],
        )
        if not selected:
            return
        self._capture_image_to(Path(selected), description="Saving scope PNG image")

    def _capture_image_to(self, path: Path, description: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        rearm = self.rearm_after_image_var.get()
        trigger_channel = self._trigger_channel_or_none()

        def job():
            def action(scope):
                scope.save_image_path(str(path))
                if rearm and hasattr(scope, "rearm_trigger_after_image"):
                    scope.rearm_trigger_after_image(trigger_channel=trigger_channel)
                return str(path)

            saved = self._new_scope_session(action)
            return {"preview_path": saved}

        self._run_job(description, job)

    def save_csv(self) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"scope_waveform_{timestamp}.csv"
        selected = filedialog.asksaveasfilename(
            title="Save enabled channel waveforms to CSV",
            initialdir=str(self.output_folder),
            initialfile=default_name,
            defaultextension=".csv",
            filetypes=[("CSV file", "*.csv"), ("All files", "*.*")],
        )
        if not selected:
            return
        path = Path(selected)
        path.parent.mkdir(parents=True, exist_ok=True)

        def job():
            def action(scope):
                scope.save_all_channels_to_single_csv(str(path))
                return str(path)

            saved = self._new_scope_session(action)
            return {"saved_path": saved}

        self._run_job("Saving enabled channel waveforms to CSV", job)

    def save_settings(self) -> None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"dpo4054_setup_{timestamp}.json"
        selected = filedialog.asksaveasfilename(
            title="Save scope settings JSON",
            initialdir=str(self.output_folder),
            initialfile=default_name,
            defaultextension=".json",
            filetypes=[("JSON file", "*.json"), ("All files", "*.*")],
        )
        if not selected:
            return
        path = Path(selected)
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
            initialdir=str(self.output_folder),
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
