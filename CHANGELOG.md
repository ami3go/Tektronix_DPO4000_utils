# Changelog

## v0.4.0 - 2026-08-26

### Removed

- Removed the Tk desktop frontend and all Tk-specific modules.
- Removed the `dpo4000-gui` console command; `dpo4000-desk` is now the only GUI entry point.
- Removed archived historical Tk GUI snapshots.
- Removed Tk-specific tests and obsolete PySide6-vs-Tk refactoring notes.

### Changed

- Package version bumped to `0.4.0`.
- DPO4000 Desk/PySide6 is now the sole supported desktop application.
- `dpo4000_utils.gui` now contains only framework-neutral filename/preferences helpers and packaged assets; it is not a frontend.
- The lazy `dpo4000_utils.gui_qt.QtScopeWindow` export now resolves to the API-only adapter.
- The Windows helper `scripts/run_gui.bat` now launches the PySide6 application.
- Added a dedicated PySide6 CI job using the offscreen Qt platform plugin.
- Architecture tests now enforce that the package has no `tkinter` imports.

### Compatibility

- The reusable Python driver/API remains available under `dpo4000_utils` and legacy `tektronix_utils` driver imports remain supported.
- Applications importing the removed Tk GUI modules must migrate to `dpo4000_utils.gui_qt` or the `dpo4000-desk` command.

## v0.3.0 - 2026-08-26

### Added

- Public `scope_session()` context manager for short-lived, driver-owned instrument sessions.
- `DPO4000Scope` constructor options for VISA timeout, read termination, and write termination.
- API-only adapters for both launched GUIs: `gui.api_scope_gui.ScopeGui` and `gui_qt.api_window.QtScopeWindow`.
- Architecture tests that prevent the launched GUI adapters from accessing `scope.scope` or raw hardcopy/settings/waveform transfer helpers.
- `docs/architecture.md` describing the enforced GUI-to-driver boundary.

### Changed

- Package version bumped to `0.3.0`.
- Tkinter and DPO4000 Desk launch paths now delegate instrument operations to the public `dpo4000_utils` API instead of owning SCPI/VISA behavior.
- Screen capture now goes through `save_image_path()`; waveform export goes through `save_all_channels_to_single_csv()`; setup restore goes through `apply_scope_settings()`.
- Channel, MATH, measurement, acquisition, trigger, and display actions in the launched Qt GUI now use the corresponding public driver methods and configuration dataclasses.
- VISA timeout and line termination are applied by `ConnectionMixin` before the initial `*IDN?` query, improving raw TCP socket behavior.
- Failed connection setup now closes both the partially opened VISA resource and resource manager.
- Raw TCP socket resource validation now rejects ports above 65535.

### Compatibility

- Existing GUI inheritance modules remain available for widget/layout compatibility and historical imports, but the launched applications use the API-only adapter layer as their instrument boundary.
- Existing `DPO4054(resource_name, auto_connect=...)` calls remain compatible; new session arguments are keyword-only.

## v0.2.1 - 2026-08-26

### Added

- Promoted current DPO4000 Desk scope actions into reusable `dpo4000_utils` APIs.
- Public payload dataclasses: `ChannelConfig`, `MathConfig`, `AcquisitionConfig`, `DisplayConfig`, and `MeasurementSetup`.
- Channel, MATH, acquisition, display, and measurement setup helpers used by DPO4000 Desk.
- Record-length helpers supporting common labels and arbitrary positive integer point counts.

### Changed

- Package version bumped to `0.2.1`.
- Package root exports the GUI-backed configuration dataclasses for direct script use.

## v0.2.0 - 2026-08-22

### Added

- **DPO4000 Desk** desktop application and `dpo4000-desk` console command.
- Modern frameless titlebar with page buttons.
- File and Display pages, measurement management, runtime GUI smoke tests, and Windows/Linux packaging workflows.

### Notes

- Python distribution name remains `dpo4000-utils` and the Python import remains `dpo4000_utils`.
- Real instrument access requires a VISA runtime/backend on the target PC.
