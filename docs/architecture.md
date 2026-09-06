# Architecture: PySide6 frontend, driver-owned instrument behavior

As of **v0.7.0**, DPO4000 Desk is the only desktop frontend and is implemented with PySide6.

```text
PySide6 widgets / Automation / Logger
              |
              v
DPO4000 Desk orchestration
              |
              v
async _run_action(description, callback, on_success, on_error)
              |
              v
PersistentScopeSession facade (GUI thread)
              |
        queued Qt request
              |
              v
dedicated PersistentScopeWorker QThread
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
              +-- ReferenceMixin
              +-- BusMixin
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

The GUI owns presentation/orchestration concerns: dialogs, destination folders, generated filenames, preview rendering, widget state, preferences, logging, keyboard shortcuts, Automation/Logger state machines, and asynchronous worker dispatch.

`tests/test_gui_driver_boundary.py` recursively enforces the raw VISA/SCPI boundary across `dpo4000_utils/gui_qt`. `tests/test_async_scope_action_contract.py` additionally protects the v0.7 asynchronous production state machines.

## Session lifecycle

`DPO4000Scope` accepts `timeout_ms`, `read_termination`, and `write_termination` settings. `ConnectionMixin.connect()` applies them before the initial identity query. Runtime updates use the public `configure_session()` method; GUI worker code does not mutate the raw VISA resource.

The launched GUI creates one `PersistentScopeSession` lazily. Its dedicated worker thread creates, uses, reconnects, and closes the retained `DPO4054` on that same thread. Requests are serialized using Qt queued connections and completion is delivered back to the GUI through callbacks/signals.

There is deliberately **no nested `QEventLoop` wait** in the production scope path. `_run_action()` returns immediately. Code that needs a result supplies `on_success` / `on_error` continuations.

`Keep session` defaults to enabled. When disabled for backend compatibility, the same worker/session architecture is used but the retained scope is closed after the operation. Transport errors invalidate the session so a later retry reconnects lazily.

`scope_session()` remains a supported framework-neutral short-lived lifecycle helper for scripts and non-retained use cases; it is no longer the normal launched-GUI lifecycle.

## Coherent parameter refresh

Connection refresh is staged as Core → REF → BUS for fault isolation and fast Core-state projection. v0.7 explicitly retains the same worker-owned scope connection across the stages. A BUS/REF capability failure therefore does not force a new connection or erase an already successful Core snapshot.

## Shutdown and cancellation

On window close, new work is stopped, pending requests are marked cancelled where possible, the retained instrument is closed on its owning worker thread, and the worker thread exits before the final window close is accepted. Threads are not forcibly terminated while VISA code is running; the configured driver timeout remains the upper bound for a backend operation that cannot cooperate sooner.

Automation fresh-Single workflows additionally use cancellation events and bounded acquisition timeouts.

## Driver calls used by DPO4000 Desk

Representative public operations include:

- `query_identity()`;
- `configure_session()`;
- `get_channel_label()` / `set_channel_label()`;
- `get_channel_configuration()` / `configure_channel()`;
- `get_math_configuration()` / `configure_math()`;
- `get_all_measurement_setups()` / `add_measurement()` / `disable_measurement()`;
- `get_trigger_level()` / `set_trigger_level()` / `configure_edge_trigger()`;
- `get_acquisition_setup()` / `configure_acquisition()`;
- `get_display_settings()` / `apply_display_settings()`;
- `get_reference_configuration()` / `configure_reference()`;
- `get_bus_configuration()` / `configure_bus()`;
- `get_decoded_bus_capability()`;
- `save_image_path()`;
- `save_all_channels_to_single_csv()`;
- `save_scope_settings()` / `apply_scope_settings()`.

Decoded BUS transaction extraction is capability-gated until hardware qualification; no undocumented command is owned by the GUI.

## GUI support package

`dpo4000_utils.gui` remains a framework-neutral support namespace for filename generation, persistent preferences, and packaged assets. It is not an alternate frontend and contains no Tk implementation.

## v0.8 composition milestone

v0.7 intentionally hardens the mature historical Qt inheritance stack rather than combining two high-risk architectural changes. v0.8 replaces that production inheritance chain with one composed `QMainWindow`, page/controller objects, and explicit runtime/preferences/output services while preserving this driver boundary and asynchronous session contract.
