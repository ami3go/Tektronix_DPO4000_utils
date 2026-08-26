# Changelog

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
- Channel configuration helpers and methods for display, scale, position, offset, coupling, bandwidth, invert, and probe gain.
- MATH waveform configuration helpers and methods for display, expression, vertical scale, and vertical position.
- Acquisition setup helpers and methods for mode, average count, and record length.
- Display/front-panel helpers and methods for backlight, waveform intensity, graticule intensity, persistence, screen text, and message clear.
- Measurement setup readback helpers for one slot or all `MEAS1..MEAS8` slots.
- `dpo4000_utils` record-length API helpers: `set_record_length()`, `get_record_length()`, `build_record_length_command()`, and `build_record_length_query()`.
- Record-length normalization for common labels such as `1k`, `10k`, `100k`, `1M`, and `10M`, plus arbitrary positive integer point counts.

### Changed

- Package version bumped to `0.2.1`.
- Package root now exports the GUI-backed configuration dataclasses for direct script use.

## v0.2.0 - 2026-08-22

### Added

- **DPO4000 Desk** name for the desktop application.
- `dpo4000-desk` console command as the primary desktop application launcher.
- Modern frameless titlebar with page buttons in the title row.
- Draggable titlebar tabs with fallback manual move handling.
- Dedicated **File** and **Display** top-level pages.
- Display controls for contrast/backlight, waveform intensity, graticule intensity, persistence, and on-screen message text.
- Existing measurement manager for `MEAS1..MEAS8`:
  - read configured measurement slots
  - load selected slot into the editor
  - apply edits back to the selected slot
  - read selected measurement value
  - delete/disable selected measurement
- Larger measurement-manager action buttons for better usability.
- Runtime desktop smoke tests for the launched UI path.
- Shared PyInstaller build helper plus Windows and Linux wrapper scripts.
- Release-capable GitHub Actions workflow for Windows/Linux executable assets.
- Linux packaging helper for raw binary, `.deb`, AppImage, and Flatpak bundle release assets.

### Changed

- Main UI now uses compact custom titlebar tabs instead of a separate top menu row.
- Preview panel no longer shows the obsolete `Screen preview` title or reserved title-band gap.
- `Settings` page was renamed to **File**.
- Display-related controls were moved out of File/Settings into **Display**.
- Build target now resolves through `dpo4000_utils.gui_qt.titlebar_tabs_window.QtScopeWindow`.
- Default packaged executable name changed to `DPO4000Desk`.
- Windows release now uses `DPO4000Desk-windows.zip`, containing the `DPO4000Desk.exe` application folder, instead of forcing a fragile one-file Windows executable in CI.
- Linux release asset names are `DPO4000Desk-linux`, `dpo4000-desk_0.2.0_amd64.deb`, `DPO4000Desk-x86_64.AppImage`, and `DPO4000Desk.flatpak`.
- The old desktop command alias was removed; use `dpo4000-desk`.

### Notes

- Python package/distribution name remains `dpo4000-utils` and the Python import remains `dpo4000_utils`.
- Real instrument access still requires a VISA runtime/backend on the target PC.
- Hardware behavior was not automatically verified in CI; DPO4000/DPO4054 hardware should be checked manually before production use.
