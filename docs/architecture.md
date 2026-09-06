# Architecture: composed PySide6 frontend, driver-owned instrument behavior

As of **v0.8.0**, DPO4000 Desk is the only desktop frontend and is implemented with PySide6.

```text
QtScopeWindow(QMainWindow)  <-- production launch shell
            |
            +-- PageController / FeaturePageController
            +-- ScopeDispatchController
            +-- PreferencesController
            +-- LogController
            +-- OutputPathController
            +-- WindowChromeController
            +-- LifecycleController
            |
            +-- LegacyFeatureSurface compatibility adapter
                    |
                    +-- mature v0.7 widgets / Automation / Logger

ScopeDispatchController
            |
            v
v0.7 async _run_action(description, callback, on_success, on_error)
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

## Production composition boundary

`dpo4000_utils.gui_qt.composition.window.QtScopeWindow` is the only production top-level window. It directly inherits `QMainWindow`; no historical feature-window class appears in its MRO.

The production shell owns explicit service/controller objects:

- `ScopeDispatchController` — the one scope-action gateway dependency;
- `PageController` plus named `FeaturePageController` objects — lazy page construction and navigation;
- `PreferencesController` — persistent GUI preferences;
- `LogController` — application log routing;
- `OutputPathController` — destination/output-path routing;
- `WindowChromeController` — frameless-window drag/minimize/maximize/close behavior;
- `LifecycleController` — shutdown of the embedded feature surface and its asynchronous runtime.

The mature v0.7 feature implementation is retained behind `composition/legacy_surface.py`. That adapter is intentionally the only composition module permitted to import the historical `*_window` stack. The old modules are compatibility implementation shims, not production ancestors. This boundary lets individual feature implementations be extracted or replaced without changing the production shell or public driver contract.

## Driver boundary rule

Desktop GUI code must not:

- access `DPO4000Scope.scope` directly;
- issue SCPI through the underlying PyVISA object;
- parse hardcopy byte streams;
- implement setup JSON restore logic;
- implement waveform acquisition/CSV transfer logic;
- configure raw VISA timeout or line termination itself.

The GUI owns presentation/orchestration concerns: dialogs, destination folders, generated filenames, preview rendering, widget state, preferences, logging, keyboard shortcuts, Automation/Logger state machines, and asynchronous worker dispatch.

`tests/test_gui_driver_boundary.py` protects the public-driver boundary. `tests/test_gui_qt_composition_architecture.py` protects the v0.8 composition boundary: shallow launch MRO, one approved legacy adapter, explicit controller dependencies, and no raw VISA/SCPI ownership in the composition layer. `tests/test_async_scope_action_contract.py` continues to protect the asynchronous state machines introduced in v0.7.

## Session lifecycle

`DPO4000Scope` accepts `timeout_ms`, `read_termination`, and `write_termination` settings. `ConnectionMixin.connect()` applies them before the initial identity query. Runtime updates use the public `configure_session()` method; GUI worker code does not mutate the raw VISA resource.

The feature runtime creates one `PersistentScopeSession` lazily. Its dedicated worker thread creates, uses, reconnects, and closes the retained `DPO4054` on that same thread. Requests are serialized using Qt queued connections and completion is delivered back to the GUI through callbacks/signals. v0.8 routes all feature-surface `_run_action()` calls through the composed `ScopeDispatchController` before they enter that runtime.

There is deliberately **no nested `QEventLoop` wait** in the production scope path. Scope submission returns immediately. Code that needs a result supplies `on_success` / `on_error` continuations.

`Keep session` defaults to enabled. When disabled for backend compatibility, the same worker/session architecture is used but the retained scope is closed after the operation. Transport errors invalidate the session so a later retry reconnects lazily.

`scope_session()` remains a supported framework-neutral short-lived lifecycle helper for scripts and non-retained use cases; it is not the normal launched-GUI lifecycle.

## Page lifecycle

The production shell exposes eight named page controllers: Connection, Channels, Measurement, Trigger, Acquisition, File, Display, and Log. `PageController.ensure_built()` owns the production lazy-build trigger and delegates the mature page builder only through the compatibility surface. `PageController.select()` owns navigation state and delegates projection into the current feature surface.

This keeps the production page registry explicit even while mature page widget implementations are being retired incrementally.

## Coherent parameter refresh

Connection refresh is staged as Core → REF → BUS for fault isolation and fast Core-state projection. The same worker-owned scope connection is retained across the stages. A BUS/REF capability failure therefore does not force a new connection or erase an already successful Core snapshot.

## Shutdown and cancellation

The composed top-level window delegates shutdown to `LifecycleController`, which closes the compatibility feature surface. The mature close chain stops Automation and Logger activity, marks cooperative cancellations, closes the retained instrument on its owning worker thread, and tears down the worker safely. Threads are not forcibly terminated while VISA code is running; the configured driver timeout remains the upper bound for a backend operation that cannot cooperate sooner.

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

## Migration policy

New production behavior belongs in the composition controllers/services or framework-neutral driver/runtime modules. New inheritance layers must not be added to the production launch path. Legacy `*_window.py` modules may be changed only to preserve compatibility or while extracting a feature behind the adapter. The adapter itself is an explicit migration seam and must not grow raw transport or SCPI responsibilities.
