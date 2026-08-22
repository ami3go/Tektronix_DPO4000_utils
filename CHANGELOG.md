# Changelog

## v0.2.0 - 2026-08-22

### Added

- PySide6 GUI launch path promoted to the main application flow.
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
- Runtime Qt smoke tests for the launched UI path.
- Shared PyInstaller build helper plus Windows and Linux wrapper scripts.
- Release-capable GitHub Actions workflow for Windows/Linux executable assets.

### Changed

- Main UI now uses compact custom titlebar tabs instead of a separate top menu row.
- Preview panel no longer shows the obsolete `Screen preview` title or reserved title-band gap.
- `Settings` page was renamed to **File**.
- Display-related controls were moved out of File/Settings into **Display**.
- Build target now resolves through `dpo4000_utils.gui_qt.titlebar_tabs_window.QtScopeWindow`.

### Notes

- Real instrument access still requires a VISA runtime/backend on the target PC.
- Hardware behavior was not automatically verified in CI; DPO4000/DPO4054 hardware should be checked manually before production use.
