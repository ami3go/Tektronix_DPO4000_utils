# Architecture: driver owns instrument behavior

Starting with **v0.3.0**, the launched Tkinter GUI and DPO4000 Desk use a strict application boundary:

```text
Tkinter / PySide6 widgets
        |
        v
GUI API adapter (UI orchestration only)
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

Launched GUI code must not:

- access `DPO4000Scope.scope` directly;
- issue SCPI through the underlying PyVISA object;
- parse hardcopy byte streams;
- implement setup JSON restore logic;
- implement waveform acquisition/CSV transfer logic;
- configure raw VISA timeout or line termination itself.

The GUI may still own presentation concerns such as dialogs, destination folders, generated filenames, preview rendering, widget state, preferences, logging, and background-worker orchestration.

## Public driver calls used by the GUI

Representative calls are:

- `scope_session(...)` for short-lived connection lifecycle;
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

## Session configuration

`DPO4000Scope` now accepts optional `timeout_ms`, `read_termination`, and `write_termination` constructor settings. `ConnectionMixin.connect()` applies these settings immediately after opening the VISA resource and **before the initial `*IDN?` query**. This matters especially for raw TCP socket resources that require newline termination.

The convenience `scope_session()` context manager is the preferred frontend path. It opens a short-lived `DPO4054`, applies driver-owned session configuration, yields the public driver object, and always disconnects it.

## Compatibility layers

The repository retains older GUI inheritance modules because they contain mature widget/layout behavior and preserve historical imports. They are no longer the launched instrument-control boundary: the final Tk and Qt entry points are `gui.api_scope_gui.ScopeGui` and `gui_qt.api_window.QtScopeWindow`, respectively.

Architecture tests verify that those launched adapters do not regress to raw VISA access.
