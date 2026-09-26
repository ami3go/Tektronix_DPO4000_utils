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
                    +-- mature v0.7 widgets / Automation / Logger / File
                    +-- composition/pages/connection.py
                    +-- composition/pages/trigger.py
                    +-- composition/pages/recipe.py
                    +-- composition/pages/scientific_export.py

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
            +-- A15 RecipeSequencer (inside one worker action)
            |       |
            |       +-- validated public driver calls
            |       +-- monotonic Delay / pause / cancel / retry
            |
            +-- A21 Desk export action
            |       |
            |       +-- public read_enabled_waveforms()
            |       +-- framework-neutral scientific exporter
            |
            v
DPO4054 / DPO4000Scope public API
            |
            +-- ConnectionMixin
            +-- ChannelMixin
            +-- TriggerMixin
            +-- AcquisitionModeReadbackMixin
            +-- AcquisitionStateMixin
            +-- AdvancedTriggerMixin
            +-- ControlMixin
            +-- HardcopyMixin
            +-- WaveformMixin
            +-- SettingsMixin
            +-- ReferenceMixin
            +-- BusMixin
            |
            v
PyVISA / VISA backend / oscilloscope

A15 RecipeResult
            |
            v
recipe_result_values()
            |
            v
A16 RuleEngine (local / framework-neutral / no instrument I/O)
            |
            +-- PASS / FAIL / INVALID
            +-- scalar/range/delta rules
            +-- AND / OR / NOT composition

WaveformData / already-acquired traces
            |
            v
A21 scientific_export (framework-neutral / no instrument I/O)
            |
            +-- lossless NumPy NPZ
            +-- portable DPOZ (manifest + raw + CSV)
            +-- deterministic import / round-trip
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

The mature v0.7 feature implementation is retained behind `composition/legacy_surface.py`. That adapter is intentionally the only composition module permitted to import the historical `*_window` stack. The old modules are compatibility implementation shims, not production ancestors. This boundary lets individual feature implementations be extracted or extended without changing the production shell or public driver contract.

Connection, Trigger, and Recipe are composition-owned page builders. `composition/pages/trigger.py` is the A14 migration boundary for Advanced Trigger UI. `composition/pages/recipe.py` is the A15/A16 Test Recipe + Pass/Fail surface. A21 deliberately does **not** replace the mature File page: `ComposedFeatureSurface._build_file_tab()` first builds the existing File page and then attaches the composition-owned `ScientificExportPanel` from `composition/pages/scientific_export.py`.

## A15 recipe execution boundary

`dpo4000_utils.recipe` is framework-neutral. It owns the versioned recipe model, structural validation, whole-recipe method/signature preflight, monotonic Delay semantics, bounded retry/backoff, pause/resume/cancel state, and ordered step results.

A Desk recipe is submitted as **one** `_run_action(..., retain_session=True)` operation. The callback receives the worker-owned public `DPO4000Scope` instance and constructs `RecipeSequencer(scope)` there. Recipe steps are serialized with every other scope operation and never obtain a second GUI-thread session.

The recipe format does not expose arbitrary SCPI, Python expressions, imports, shell commands, or private/dotted attribute access. Session/transport lifecycle methods and `probe_scpi_query` remain unavailable to recipes.

Pause/cancel are cooperative. Delay and retry waits are interruptible; paused wall time does not consume a Delay budget. A public driver method already executing is not forcibly interrupted from another thread because that would violate worker/session ownership.

This engine is a reuse boundary for later features: A16 consumes recipe values/results; A18 can consume recipe/result artifacts plus A16 decisions; A25 can reuse the same schema and sequencer without Qt.

## A16 pass/fail evaluation boundary

`dpo4000_utils.rules` is framework-neutral and owns no instrument lifecycle. It accepts a caller-provided mapping of values and returns a deterministic decision tree.

Supported scalar rules include numeric comparisons, inclusive ranges, absolute delta, and relative delta. Logical composition uses three-state `AND` / `OR` / `NOT` semantics. Missing, non-numeric, NaN, Inf, or otherwise unusable inputs produce `INVALID`; such inputs never silently become `PASS`.

`recipe_result_values()` is the A15→A16 adapter. Every completed A15 step is addressable by index/name; unique names are promoted directly, and dataclass/mapping results are flattened with dot-separated keys.

A16 does not evaluate Python expressions, import modules, execute shell commands, own SCPI, or implement sequencing/branching. In Desk it runs only after an A15 recipe reaches `COMPLETED` and performs no second worker action or VISA session.

## A21 scientific export boundary

`dpo4000_utils.scientific_export` is framework-neutral and owns **no instrument I/O**. Its input is `WaveformData` that has already been acquired through the public driver or produced by another trusted source.

A21 supports two versioned archive surfaces:

- **NPZ** — NumPy-native raw/X/Y arrays plus a UTF-8 JSON manifest, always imported with `allow_pickle=False`;
- **DPOZ** — portable ZIP containing `manifest.json`, exact little-endian raw samples, and one scaled CSV trace per waveform.

Both formats preserve enough information to reconstruct `WaveformData`: source/label, transfer range, requested encoding, acquisition timestamp, raw sample type/content, and the full `WaveformPreamble`. Export and import therefore form a deterministic raw-data round trip rather than only a convenience CSV conversion.

A21 validates schema/version, unknown fields, trace/sample limits, raw byte/dtype/shape consistency, finite metadata/scaling values, duplicate sources, and floating raw sample finiteness. DPOZ is read directly from deterministic archive member names and is never extracted onto the filesystem. NPZ import does not permit pickle/object loading.

File finalization is atomic: a same-directory temporary file is completely written and closed, then `os.replace()` swaps it into the destination. On failure the temporary file is removed and an existing destination remains unchanged.

A21 is intentionally independent of A18 Evidence Bundle and A20 Measurement Trend Dashboard. Those future features may feed already-collected data into A21, but A21 neither imports nor requires their models. This lets scientific export remain a reusable storage boundary for scripts, Desk, future evidence bundles, trends, and A25 headless jobs.

### Desk execution model

The File-page A21 panel submits one `_run_action(..., retain_session=True)` callback. Inside the scope worker the callback:

1. acquires enabled channels using public `read_enabled_waveforms()`;
2. creates the NPZ/DPOZ archive with `export_scientific_dataset()`;
3. returns `ScientificExportResult` throughput metrics to the GUI continuation.

This means both waveform transfer and potentially expensive 1M-point serialization/file I/O run outside the Qt GUI thread. The GUI callback only projects status/metrics. No raw `.scope`, `.query()`, `.write()`, or `ResourceManager` access is allowed in the A21 panel.

Headless scientific export can bypass Qt entirely by acquiring `WaveformData` through the public driver and then calling `export_scientific_dataset()` directly.

## Driver boundary rule

Desktop GUI code must not:

- access `DPO4000Scope.scope` directly;
- issue SCPI through the underlying PyVISA object;
- parse hardcopy byte streams;
- implement setup JSON restore logic;
- implement waveform acquisition/CSV/scientific-transfer protocol logic;
- configure raw VISA timeout or line termination itself.

The GUI owns presentation/orchestration concerns: dialogs, destination paths, generated filenames, preview rendering, widget state, preferences, logging, keyboard shortcuts, Automation/Logger/Recipe state projection, rule-set editing/result projection, A21 export choices/status projection, and asynchronous worker dispatch.

`tests/test_gui_driver_boundary.py` protects the public-driver boundary. A14, A15, and A16 add focused feature contracts. A21 adds exact archive round-trip/atomicity/schema tests plus `tests/test_a21_scientific_export_gui_contract.py`, which locks the File-page extension and raw-transport prohibition. `tests/test_gui_qt_composition_architecture.py` continues to protect the shallow production composition boundary.

## Session lifecycle

`DPO4000Scope` accepts `timeout_ms`, `read_termination`, and `write_termination` settings. `ConnectionMixin.connect()` applies them before the initial identity query. Runtime updates use public `configure_session()`; GUI worker code does not mutate the raw VISA resource.

The feature runtime creates one `PersistentScopeSession` lazily. Its dedicated worker thread creates, uses, reconnects, and closes the retained `DPO4054` on that same thread. Requests are serialized using Qt queued connections and completion is delivered back to the GUI through callbacks/signals.

There is deliberately **no nested `QEventLoop` wait** in the production scope path. Scope submission returns immediately. A14 readbacks use continuations; A15 runs per-step work in the scope worker; A16 consumes completed recipe results locally; A21 captures and serializes waveform data inside a worker action then returns metrics to the GUI.

`Keep session` defaults to enabled. When disabled for backend compatibility, the same worker/session architecture is used but the retained scope is closed after the operation. Transport errors invalidate the session so a later retry reconnects lazily.

`scope_session()` remains a supported framework-neutral short-lived lifecycle helper for scripts and non-retained use cases; it is not the normal launched-GUI lifecycle.

## Page lifecycle

The canonical production layout exposes eleven pages: Connection, Channels, Measurement, Trigger, Acquisition, Automation, Recipe, Logger, File, Display, and Log. `PageController.ensure_built()` owns lazy construction and `PageController.select()` owns navigation state.

Recipe is inserted between Automation and Logger. Existing shortcuts remain stable. A16 extends Recipe rather than adding a new top-level page. A21 likewise extends the existing File page rather than adding a twelfth page, because scientific export is another output/storage operation alongside the existing image/CSV/settings capabilities.

## Coherent parameter refresh

Connection refresh is staged as Core → REF → BUS for fault isolation and fast Core-state projection. The same worker-owned scope connection is retained across the stages. A BUS/REF capability failure therefore does not force a new connection or erase an already successful Core snapshot.

## Shutdown and cancellation

The composed top-level window delegates shutdown to `LifecycleController`, which closes the compatibility feature surface. The mature close chain stops Automation and Logger activity, marks cooperative cancellations, closes the retained instrument on its owning worker thread, and tears down the worker safely. Threads are not forcibly terminated while VISA code is running; configured driver timeouts remain the upper bound for backend operations that cannot cooperate sooner.

A15 Recipe cancellation uses its cooperative checkpoint path. A16 has no asynchronous activity of its own. A21 currently runs as one serialized worker action; it does not spawn additional exporter threads or retain background file handles after completion.

## Driver calls used by DPO4000 Desk

Representative public operations include:

- `query_identity()`;
- `configure_session()`;
- `get_channel_label()` / `set_channel_label()`;
- `get_channel_configuration()` / `configure_channel()`;
- `get_math_configuration()` / `configure_math()`;
- `get_all_measurement_setups()` / `add_measurement()` / `disable_measurement()`;
- trigger and Sequence/B-trigger configuration/readback;
- acquisition configuration/state operations;
- display, REF, BUS, screenshot, settings, and CSV operations;
- `read_waveform()` / `read_channel_waveform_data()` / `read_enabled_waveforms()`.

A21's `export_scientific_dataset()` / `import_scientific_dataset()` are framework utilities, not driver transport methods. They can be reused without a connected oscilloscope.

`probe_scpi_query()` is a driver-level qualification utility rather than a normal GUI or recipe operation. It temporarily caps the active VISA timeout, treats a timeout as unsupported only after recovery/health validation, and restores the prior timeout exactly.

Decoded BUS transaction extraction remains capability-gated until qualified; no undocumented command is owned by the GUI.

## GUI support package

`dpo4000_utils.gui` remains a framework-neutral support namespace for filename generation, persistent preferences, and packaged assets. It is not an alternate frontend and contains no Tk implementation.

## Migration policy

New production behavior belongs in composition controllers/services or framework-neutral driver/runtime modules. New inheritance layers must not be added to the production launch path. Legacy `*_window.py` modules may be changed only to preserve compatibility or while extracting/extending a feature behind the adapter. The adapter itself is an explicit migration seam and must not grow raw transport or SCPI responsibilities.
