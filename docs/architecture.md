# Architecture: PySide6 frontend, driver-owned instrument behavior

Starting with **v0.4.0**, DPO4000 Desk is the only desktop frontend and is implemented with PySide6.

```text
PySide6 widgets
      |
      v
DPO4000 Desk UI orchestration
      |
      v
gui_qt.api_window.QtScopeWindow
      |
      v
dpo4000_utils.scope_session()
      |
      v
DPO4054 / DPO4000Scope public API
      |
      +-- ConnectionMixin
      +-- ChannelMixin
      +-- TriggerMixin
      +-- ControlMixin
      +-- HardcopyMixin
      +-- WaveformMixin
      +-- SettingsMixin
      |
      v
PyVISA / VISA backend / oscilloscope
```

## Boundary rule

Desktop GUI code must not:

- access `DPO4000Scope.scope` directly;
- issue SCPI through the underlying PyVISA object;
- parse hardcopy byte streams;
- implement setup JSON restore logic;
- implement waveform acquisition/CSV transfer logic;
- configure raw VISA timeout or line termination itself.

The GUI owns presentation concerns: dialogs, destination folders, generated filenames, preview rendering, widget state, preferences, logging, keyboard shortcuts, and background-worker orchestration.

## Driver calls used by DPO4000 Desk

Representative public operations include:

- `scope_session(...)`;
- `query_identity()`;
- `get_channel_label()` / `set_channel_label()`;
- `get_channel_configuration()` / `configure_channel()`;
- `get_math_configuration()` / `configure_math()`;
- `get_all_measurement_setups()` / `add_measurement()` / `disable_measurement()`;
- `get_trigger_level()` / `set_trigger_level()` / `configure_edge_trigger()`;
- `get_acquisition_setup()` / `configure_acquisition()`;
- `get_display_settings()` / `apply_display_settings()`;
- `save_image_path()`;
- `save_all_channels_to_single_csv()`;
- `save_scope_settings()` / `apply_scope_settings()`.

## Session lifecycle

`DPO4000Scope` accepts optional `timeout_ms`, `read_termination`, and `write_termination` constructor settings. `ConnectionMixin.connect()` applies these immediately after opening the VISA resource and before the initial `*IDN?` query.

`scope_session()` is the preferred frontend lifecycle helper. It opens a short-lived `DPO4054`, applies driver-owned session settings, yields the public driver object, and always disconnects it.

## GUI support package

`dpo4000_utils.gui` remains only as a framework-neutral support namespace for filename generation, persistent preferences, and packaged assets. It is not an alternate frontend and contains no Tk implementation.

## Enforcement

`tests/test_gui_driver_boundary.py` verifies that:

- `dpo4000-desk` resolves to the PySide6 runner;
- the API adapter does not access `scope.scope`;
- the API adapter does not import low-level hardcopy/settings/waveform transfer helpers;
- Python source under `dpo4000_utils` contains no `tkinter` imports.
