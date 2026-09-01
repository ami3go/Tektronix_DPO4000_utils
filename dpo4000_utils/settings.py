"""Save and restore validated Tektronix scope setup strings."""

from __future__ import annotations

import json
import logging
import time
import warnings
from datetime import datetime
from pathlib import Path
from typing import Any

from .connection import temporary_session_attributes
from .errors import (
    DPOError,
    DPOSettingsError,
    DPOTimeoutError,
    is_timeout_error,
    is_transport_error,
    transport_exception,
)

logger = logging.getLogger(__name__)

SETTINGS_SCHEMA_VERSION = 1
SETUP_FORMAT = "tektronix_scpi_lrn"
MAX_SETUP_LENGTH = 4_000_000


def resolve_settings_path(
    file_name: str | Path | None,
    *,
    settings_folder: str | Path,
    default_prefix: str = "dpo4054_setup",
) -> Path:
    """Resolve a settings JSON path without creating filesystem state."""
    folder = Path(settings_folder)
    if file_name is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = folder / f"{default_prefix}_{timestamp}.json"
    else:
        file_path = Path(file_name)
        if not file_path.is_absolute() and file_path.parent == Path():
            file_path = folder / file_path
        if file_path.suffix == "":
            file_path = file_path.with_suffix(".json")
    return file_path


def _parse_identity(identity: str) -> tuple[str, str]:
    parts = [part.strip() for part in str(identity or "").split(",")]
    manufacturer = parts[0].upper() if parts and parts[0] else ""
    model = parts[1].upper() if len(parts) > 1 and parts[1] else ""
    return manufacturer, model


def _is_tektronix(manufacturer: str) -> bool:
    return manufacturer.upper().startswith("TEK")


def _model_family(model: str) -> str:
    token = model.upper().replace("-", "")
    if token.startswith(("DPO4", "MSO4")):
        return "4000"
    return ""


def _query_identity(scope: Any) -> str:
    try:
        return str(scope.query("*IDN?")).strip()
    except DPOError:
        raise
    except Exception as exc:
        if is_transport_error(exc):
            raise transport_exception(exc, "Reading oscilloscope identity") from exc
        raise DPOSettingsError(f"Could not read oscilloscope identity: {exc}") from exc


def read_scope_setup_string(scope: Any) -> str:
    """Read the current setup string using *LRN? with SET? compatibility fallback."""
    try:
        return str(scope.query("*LRN?")).strip()
    except Exception as first_exc:
        if is_transport_error(first_exc):
            raise transport_exception(first_exc, "Reading scope setup with *LRN?") from first_exc
        try:
            return str(scope.query("SET?")).strip()
        except Exception as second_exc:
            if is_transport_error(second_exc):
                raise transport_exception(second_exc, "Reading scope setup with SET?") from second_exc
            raise DPOSettingsError(
                f"Scope setup could not be read with *LRN? or SET?: {second_exc}"
            ) from second_exc


def validate_scope_settings_payload(
    data: Any,
    *,
    connected_identity: str | None = None,
    allow_legacy: bool = True,
    allow_incompatible: bool = False,
) -> dict[str, Any]:
    """Validate setup JSON structure and optional instrument compatibility."""
    if not isinstance(data, dict):
        raise DPOSettingsError("Invalid setup file: top-level JSON value must be an object.")

    schema_version = data.get("schema_version")
    if schema_version is None:
        if not allow_legacy:
            raise DPOSettingsError("Invalid setup file: missing 'schema_version'.")
    else:
        try:
            schema_value = int(schema_version)
        except (TypeError, ValueError) as exc:
            raise DPOSettingsError("Invalid setup file: 'schema_version' must be an integer.") from exc
        if schema_value != SETTINGS_SCHEMA_VERSION:
            raise DPOSettingsError(
                f"Unsupported settings schema_version={schema_value}; "
                f"expected {SETTINGS_SCHEMA_VERSION}."
            )

    setup_format = data.get("setup_format")
    if setup_format is None:
        if not allow_legacy:
            raise DPOSettingsError("Invalid setup file: missing 'setup_format'.")
    elif str(setup_format).strip().lower() != SETUP_FORMAT:
        raise DPOSettingsError(
            f"Unsupported setup_format={setup_format!r}; expected {SETUP_FORMAT!r}."
        )

    setup_string = data.get("setup")
    if not isinstance(setup_string, str) or not setup_string.strip():
        raise DPOSettingsError("Invalid setup file: missing or empty 'setup' field.")
    if len(setup_string) > MAX_SETUP_LENGTH:
        raise DPOSettingsError(
            f"Invalid setup file: setup string exceeds {MAX_SETUP_LENGTH} characters."
        )

    saved_identity = str(data.get("instrument", "") or "").strip()
    saved_manufacturer, saved_model = _parse_identity(saved_identity)
    current_manufacturer, current_model = _parse_identity(connected_identity or "")

    if (
        saved_model
        and saved_manufacturer
        and not _is_tektronix(saved_manufacturer)
        and not allow_incompatible
    ):
        raise DPOSettingsError(
            f"Settings were saved from non-Tektronix instrument {saved_identity!r}."
        )

    # An unparseable/legacy identity such as "Unknown" is not enough evidence to
    # reject. A normal *IDN? response includes both manufacturer and model.
    if (
        current_model
        and current_manufacturer
        and not _is_tektronix(current_manufacturer)
        and not allow_incompatible
    ):
        raise DPOSettingsError(
            f"Connected instrument is not Tektronix: {connected_identity!r}."
        )

    if saved_model and current_model:
        saved_family = _model_family(saved_model)
        current_family = _model_family(current_model)
        if saved_family and current_family and saved_family == current_family:
            if saved_model != current_model:
                warnings.warn(
                    f"Applying settings saved on {saved_model} to compatible {current_model}; "
                    "model-specific options may differ.",
                    RuntimeWarning,
                    stacklevel=2,
                )
        elif not allow_incompatible and saved_model != current_model:
            raise DPOSettingsError(
                f"Settings model {saved_model!r} is not compatible with connected "
                f"model {current_model!r}."
            )

    return data


def build_scope_settings_payload(scope: Any) -> dict[str, Any]:
    """Build a versioned serializable settings payload from a connected scope."""
    instrument = _query_identity(scope)
    setup = read_scope_setup_string(scope)
    if not setup:
        raise DPOSettingsError("Scope returned an empty setup string.")
    return {
        "schema_version": SETTINGS_SCHEMA_VERSION,
        "instrument": instrument,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "setup_format": SETUP_FORMAT,
        "setup": setup,
    }


def save_scope_settings_file(
    scope: Any,
    file_name: str | Path | None,
    *,
    settings_folder: str | Path,
    default_prefix: str = "dpo4054_setup",
) -> Path:
    """Save the current scope setup JSON and return the written path."""
    file_path = resolve_settings_path(
        file_name,
        settings_folder=settings_folder,
        default_prefix=default_prefix,
    )
    payload = build_scope_settings_payload(scope)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        file_path.write_text(json.dumps(payload, indent=4), encoding="utf-8")
    except OSError as exc:
        raise DPOSettingsError(f"Could not write scope setup file {file_path}: {exc}") from exc
    return file_path


def load_scope_settings_file(
    file_name: str | Path,
    *,
    settings_folder: str | Path | None = None,
    allow_legacy: bool = True,
) -> dict[str, Any]:
    """Load and structurally validate a scope settings JSON file."""
    file_path = Path(file_name)
    if settings_folder is not None and not file_path.is_absolute() and file_path.parent == Path():
        file_path = Path(settings_folder) / file_path

    if not file_path.exists():
        raise DPOSettingsError(f"Scope setup file not found: {file_path}")

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DPOSettingsError(f"Could not read valid JSON setup file {file_path}: {exc}") from exc
    return validate_scope_settings_payload(data, allow_legacy=allow_legacy)


def apply_setup_string(
    scope: Any,
    setup_string: str,
    *,
    wait_complete: bool = False,
    check_error: bool = True,
    restore_delay_s: float = 2.0,
    opc_timeout_ms: int = 30000,
) -> None:
    """Apply a validated Tektronix setup string to a connected VISA session."""
    if not isinstance(setup_string, str) or not setup_string.strip():
        raise DPOSettingsError("Setup string cannot be empty.")
    if len(setup_string) > MAX_SETUP_LENGTH:
        raise DPOSettingsError(f"Setup string exceeds {MAX_SETUP_LENGTH} characters.")

    try:
        # Clearing status here is intentional: subsequent ESR reflects the restore
        # operation rather than pre-existing status bits.
        scope.write("*CLS")
        scope.write(setup_string)
        if restore_delay_s:
            time.sleep(restore_delay_s)
    except DPOError:
        raise
    except Exception as exc:
        if is_transport_error(exc):
            raise transport_exception(exc, "Applying scope setup") from exc
        raise DPOSettingsError(f"Could not apply scope setup: {exc}") from exc

    if wait_complete:
        try:
            with temporary_session_attributes(scope, timeout=int(opc_timeout_ms)):
                scope.query("*OPC?")
        except Exception as exc:
            if is_timeout_error(exc):
                raise DPOTimeoutError(
                    "Timeout while waiting for *OPC? after restoring scope settings. "
                    "The setup may still have been applied. Try wait_complete=False, "
                    "increase opc_timeout_ms, or stop acquisition before restore."
                ) from exc
            if is_transport_error(exc):
                raise transport_exception(exc, "Waiting for scope setup completion") from exc
            if isinstance(exc, DPOError):
                raise
            raise DPOSettingsError(f"Could not wait for scope setup completion: {exc}") from exc

    if check_error:
        try:
            esr = int(str(scope.query("*ESR?")).strip())
        except Exception as exc:
            if is_transport_error(exc):
                raise transport_exception(exc, "Reading *ESR? after scope setup") from exc
            raise DPOSettingsError("Could not read *ESR? after applying scope settings.") from exc

        if esr != 0:
            try:
                error_text = str(scope.query("ALLEV?")).strip()
            except Exception as exc:
                if is_transport_error(exc):
                    raise transport_exception(exc, "Reading ALLEV? after scope setup") from exc
                error_text = f"Could not read ALLEV?: {exc}"
            raise DPOSettingsError(
                f"Scope reported error after applying setup. ESR={esr}, ALLEV={error_text}"
            )


def apply_scope_settings_file(
    scope: Any,
    file_name: str | Path,
    *,
    settings_folder: str | Path | None = None,
    wait_complete: bool = False,
    check_error: bool = True,
    restore_delay_s: float = 2.0,
    opc_timeout_ms: int = 30000,
    allow_legacy: bool = True,
    allow_incompatible: bool = False,
) -> dict[str, Any]:
    """Load, validate compatibility, and apply a saved scope setup JSON file."""
    data = load_scope_settings_file(
        file_name,
        settings_folder=settings_folder,
        allow_legacy=allow_legacy,
    )
    connected_identity = _query_identity(scope)
    validate_scope_settings_payload(
        data,
        connected_identity=connected_identity,
        allow_legacy=allow_legacy,
        allow_incompatible=allow_incompatible,
    )
    apply_setup_string(
        scope,
        data["setup"],
        wait_complete=wait_complete,
        check_error=check_error,
        restore_delay_s=restore_delay_s,
        opc_timeout_ms=opc_timeout_ms,
    )
    return data


class SettingsMixin:
    """Mixin for non-interactive JSON setup save/restore helpers."""

    def _resolve_settings_path(self, file_name: str | Path | None, default_prefix: str) -> Path:
        return resolve_settings_path(
            file_name,
            settings_folder=self.settings_folder,
            default_prefix=default_prefix,
        )

    def save_scope_settings(self, file_name=None, ask_before_overwrite=True):
        """Save current setup without interactive ``input()`` prompts.

        ``ask_before_overwrite=True`` now means "refuse to overwrite" so automation
        never blocks on stdin. GUI/CLI callers should perform their own confirmation
        and call with ``ask_before_overwrite=False`` when overwrite is approved.
        """
        scope = self.ensure_connected()
        file_path = self._resolve_settings_path(file_name, "dpo4054_setup")
        if file_path.exists() and ask_before_overwrite:
            raise FileExistsError(
                f"Scope setup file already exists: {file_path}. "
                "Confirm overwrite in the caller, then pass ask_before_overwrite=False."
            )
        file_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            file_path.write_text(
                json.dumps(build_scope_settings_payload(scope), indent=4),
                encoding="utf-8",
            )
        except OSError as exc:
            raise DPOSettingsError(f"Could not write scope setup file {file_path}: {exc}") from exc
        logger.info("Scope settings saved path=%s resource=%s", file_path, self.resource_name)
        return file_path

    def apply_scope_settings(
        self,
        file_name,
        wait_complete=False,
        check_error=True,
        restore_delay_s=2.0,
        opc_timeout_ms=30000,
        *,
        allow_legacy=True,
        allow_incompatible=False,
    ):
        """Apply oscilloscope setup from a validated saved JSON file."""
        return apply_scope_settings_file(
            self.ensure_connected(),
            file_name,
            settings_folder=self.settings_folder,
            wait_complete=wait_complete,
            check_error=check_error,
            restore_delay_s=restore_delay_s,
            opc_timeout_ms=opc_timeout_ms,
            allow_legacy=allow_legacy,
            allow_incompatible=allow_incompatible,
        )


__all__ = [
    "MAX_SETUP_LENGTH",
    "SETTINGS_SCHEMA_VERSION",
    "SETUP_FORMAT",
    "SettingsMixin",
    "apply_scope_settings_file",
    "apply_setup_string",
    "build_scope_settings_payload",
    "load_scope_settings_file",
    "read_scope_setup_string",
    "resolve_settings_path",
    "save_scope_settings_file",
    "validate_scope_settings_payload",
]
