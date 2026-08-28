# Changelog

## v0.4.10 - 2026-08-28

### Added

- Added a persistent **Read all parameters after connection** checkbox to the Connection page.
- When enabled, a successful IDN connection continues to read the complete CH/MATH/REF/BUS/measurement/trigger/acquisition/display snapshot.
- When disabled, connection testing stops after IDN for a faster lightweight connection check.

### Changed

- The read-all-parameters preference defaults to enabled to preserve existing behavior and is stored in `gui_preferences.json`.
- Package version bumped to `0.4.10`.

## v0.4.9 - 2026-08-28

### Fixed

- Updated the remaining PySide6 architecture metadata tests to follow the final `bus_window -> desktop_window -> api_window -> visual layers` launch chain after BUS support was added.

### Changed

- Package version bumped to `0.4.9`.

## v0.4.8 - 2026-08-28

### Added

- Added BUS1..BUS4 decoded bus-waveform controls to the Channels page.
- Added a reusable public `BusConfig` / `BusMixin` API for reading and configuring common BUS state/type/label/position/display properties.
- Added protocol-specific BUS configuration coverage for I²C, SPI, CAN, RS-232/UART, LIN, FlexRay, Audio, USB, and Parallel, including all per-BUS fields documented by the DPO4000 programmer manual.
- Added automatic BUS1..BUS4 readback to the post-connection scope snapshot so the GUI is populated from the instrument.
- Added BUS driver contract, snapshot isolation, and offscreen PySide6 runtime tests.

### Changed

- Parallel BUS settings remain available for MSO4000-family hardware while DPO4000 option-dependent protocols are exposed without hiding firmware-supported combinations.
- Package version bumped to `0.4.8`.

## v0.4.7 - 2026-08-28

### Added

- Added REF1..REF4 reference-waveform support to the Channels page.
- Added public high-level APIs for reading and configuring reference waveform display state, labels, vertical scale/position, horizontal scale/delay, and storage date/time.
- Added a guarded waveform-store action for copying CH1..CH4, MATH, or another REF waveform into a selected reference memory.
- Added automatic REF1..REF4 readback to the post-connection scope snapshot so reference controls are populated from the instrument.

### Changed

- Package version bumped to `0.4.7`.

## v0.4.6 - 2026-08-28

### Fixed

- Made the Qt runtime smoke test tolerant of the one-pixel frame margin reported by Qt 6.11's offscreen style engine while still enforcing that the untitled preview reserves no title band.

### Changed

- Package version bumped to `0.4.6`.

## v0.4.5 - 2026-08-28

### Fixed

- Prevented the PySide6 CI suite from entering the real GUI event loop while testing the missing-PySide dependency message; the contract is now verified without executing `runner.main()`.
- Added a ten-minute timeout to the offscreen PySide6 CI job so a future GUI-test event-loop regression cannot block the workflow indefinitely.

### Changed

- Package version bumped to `0.4.5`.

## v0.4.4 - 2026-08-28

### Fixed

- Restored Python 3.10 compatibility for TOML-based metadata tests by using the `tomli` backport when `tomllib` is unavailable.
- Added explicit Qt/EGL runtime libraries to the offscreen PySide6 CI job so importing `PySide6.QtWidgets` works on the Ubuntu runner.

### Changed

- Added `tomli` as a Python-3.10-only development dependency.
- Package version bumped to `0.4.4`.

## v0.4.3 - 2026-08-28

### Fixed

- Preserved trailing/leading underscores in safe filename parts so configured prefixes such as `scope_` and `dpo4054_` remain separators when output paths are built.
- Updated stale CI metadata tests that still targeted v0.2-era version strings, removed console aliases, and intermediate PySide6 launch classes instead of the current `desktop_window` launch boundary.
- Updated startup-debug and theme assertions to validate current behavior rather than obsolete source-text literals.

### Changed

- CI architecture checks now follow the current desktop -> API adapter -> visual inheritance chain while retaining coverage for worker-thread I/O, lazy card construction, measurement management, and PySide6 packaging.
- Package version bumped to `0.4.3`.

## v0.4.2 - 2026-08-28

### Added

- Added a single-session scope snapshot reader used immediately after a successful IDN connection.
- Added public edge-trigger readback for mode, source, slope, coupling, and the source-appropriate trigger level.

### Changed

- Successful connection now builds the lazy instrument-control pages and replaces their default values with live scope values.
- Automatic refresh covers channel labels, all four channel configurations, MATH, configured measurements, trigger setup and horizontal position, acquisition setup, and display settings.
- Switching the channel selector after connection reuses the freshly read channel snapshot instead of showing startup defaults.
- Refresh sections are isolated: a failed optional read is logged as a warning while other cards continue to populate.
- Connection and automatic-refresh failures remain non-modal and are reported in the bottom status bar.
- Package version bumped to `0.4.2`.

## v0.4.1 - 2026-08-28

### Changed

- Scope connection tests are now non-modal: successful `*IDN?` information is shown in the bottom status bar and existing IDN status chip instead of a message box.
- Connection-test failures now show the actual error text in the bottom status bar/status strip and log without opening an error dialog.
- Other scope-operation errors retain their existing modal error behavior.
- Added a final `desktop_window` presentation layer so connection-feedback UX remains separate from the API-only instrument adapter.
- Package version bumped to `0.4.1`.

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
- API-only adapters for launched PySide6 GUI operations.
- Architecture tests that prevent the launched GUI adapters from accessing `scope.scope` or raw hardcopy/settings/waveform transfer helpers.
- `docs/architecture.md` describing the enforced GUI-to-driver boundary.

### Changed

- Package version bumped to `0.3.0`.
- DPO4000 Desk launch paths delegate instrument operations to the public `dpo4000_utils` API instead of owning SCPI/VISA behavior.
- Screen capture, waveform export, setup restore, channel, MATH, measurement, acquisition, trigger, and display actions use public driver operations.
- VISA timeout and line termination are applied before the initial `*IDN?` query.
- Failed connection setup closes partially opened VISA resources.

## v0.2.1 - 2026-08-26

### Added

- Promoted DPO4000 Desk scope actions into reusable `dpo4000_utils` APIs.
- Public payload dataclasses: `ChannelConfig`, `MathConfig`, `AcquisitionConfig`, `DisplayConfig`, and `MeasurementSetup`.

### Changed

- Package version bumped to `0.2.1`.

## v0.2.0 - 2026-08-22

### Added

- **DPO4000 Desk** desktop application and `dpo4000-desk` console command.
- Modern frameless titlebar with page buttons.
- File and Display pages, measurement management, runtime GUI smoke tests, and Windows/Linux packaging workflows.

### Notes

- Python distribution name remains `dpo4000-utils` and the Python import remains `dpo4000_utils`.
- Real instrument access requires a VISA runtime/backend on the target PC.
