"""Save and restore Tektronix scope setup strings."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

try:
    from pyvisa.errors import VisaIOError
except Exception:
    VisaIOError = Exception


class SettingsMixin:
    """Mixin for JSON setup save/restore helpers."""

    def _resolve_settings_path(self, file_name: str | Path | None, default_prefix: str) -> Path:
        if file_name is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = self.settings_folder / f"{default_prefix}_{timestamp}.json"
        else:
            file_path = Path(file_name)
            if not file_path.is_absolute() and file_path.parent == Path("."):
                file_path = self.settings_folder / file_path
            if file_path.suffix == "":
                file_path = file_path.with_suffix(".json")

        file_path.parent.mkdir(parents=True, exist_ok=True)
        return file_path

    def save_scope_settings(self, file_name=None, ask_before_overwrite=True):
        """
        Save current oscilloscope setup to a JSON file.

        If file_name is not provided, a timestamped file is created in
        ``self.settings_folder``. The public behavior is compatible with the
        original DPO4054 helper, including the optional overwrite prompt.
        """
        scope = self.ensure_connected()
        file_path = self._resolve_settings_path(file_name, "dpo4054_setup")

        while file_path.exists() and ask_before_overwrite:
            answer = input(
                f"File already exists:\n{file_path}\n\nOverwrite it? [y/N]: "
            ).strip().lower()

            if answer in ("y", "yes"):
                break

            new_file_name = input("Enter new filename, or press Enter to cancel: ").strip()
            if not new_file_name:
                print("Saving cancelled.")
                return None

            file_path = self._resolve_settings_path(new_file_name, "dpo4054_setup")

        try:
            idn = scope.query("*IDN?").strip()
        except Exception:
            idn = "Unknown"

        scope.write("*CLS")

        try:
            setup_string = scope.query("*LRN?").strip()
        except Exception:
            setup_string = scope.query("SET?").strip()

        data = {
            "instrument": idn,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "setup_format": "tektronix_scpi_lrn",
            "setup": setup_string,
        }

        file_path.write_text(json.dumps(data, indent=4), encoding="utf-8")
        print(f"Scope settings saved to: {file_path}")
        return file_path

    def apply_scope_settings(
        self,
        file_name,
        wait_complete=False,
        check_error=True,
        restore_delay_s=2.0,
        opc_timeout_ms=30000,
    ):
        """
        Apply oscilloscope setup from a saved JSON file.

        ``wait_complete`` defaults to False because some older DPO4000 firmware
        can time out on ``*OPC?`` after a long setup restore even when the setup
        was applied.
        """
        scope = self.ensure_connected()

        file_path = Path(file_name)
        if not file_path.is_absolute() and file_path.parent == Path("."):
            file_path = self.settings_folder / file_path

        if not file_path.exists():
            raise FileNotFoundError(f"Scope setup file not found: {file_path}")

        data = json.loads(file_path.read_text(encoding="utf-8"))
        setup_string = data.get("setup")
        if not setup_string:
            raise ValueError("Invalid setup file: missing or empty 'setup' field.")

        scope.write("*CLS")
        scope.write(setup_string)
        time.sleep(restore_delay_s)

        if wait_complete:
            old_timeout = scope.timeout
            try:
                scope.timeout = opc_timeout_ms
                scope.query("*OPC?")
            except VisaIOError as exc:
                raise TimeoutError(
                    "Timeout while waiting for *OPC? after restoring scope settings. "
                    "The setup may still have been applied. Try wait_complete=False, "
                    "increase opc_timeout_ms, or stop acquisition before restore."
                ) from exc
            finally:
                scope.timeout = old_timeout

        if check_error:
            try:
                esr = int(scope.query("*ESR?").strip())
            except Exception as exc:
                raise RuntimeError("Could not read *ESR? after applying scope settings.") from exc

            if esr != 0:
                try:
                    error_text = scope.query("ALLEV?").strip()
                except Exception:
                    error_text = "Could not read ALLEV?"
                raise RuntimeError(
                    f"Scope reported error after applying setup. ESR={esr}, ALLEV={error_text}"
                )

        return data
