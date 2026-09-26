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
                    +-- composition/pages/connection.py
                    +-- composition/pages/trigger.py
                    +-- composition/pages/recipe.py

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

Connection, Trigger, and Recipe are composition-owned page builders. `composition/pages/trigger.py` is the A14 migration boundary for Advanced Trigger UI. It preserves mature acquisition/trigger-level/horizontal/re-arm widgets where useful, but type-specific A-trigger, holdoff, and B-trigger configuration is newly built in composition and dispatched only through public driver calls. `composition/pages/recipe.py` is the A15/A16 Test Recipe + Pass/Fail surface; it edits/validates versioned JSON, submits the complete recipe through the asynchronous scope gateway, then evaluates A16 rules locally after a completed recipe result is returned.

## A15 recipe execution boundary

`dpo4000_utils.recipe` is framework-neutral. It owns the versioned recipe model, structural validation, whole-recipe method/signature preflight, monotonic Delay semantics, bounded retry/backoff, pause/resume/cancel state, and ordered step results.

A Desk recipe is submitted as **one** `_run_action(..., retain_session=True)` operation. The callback receives the worker-owned public `DPO4000Scope` instance and constructs `RecipeSequencer(scope)` there. This is intentional: recipe steps are serialized with every other scope operation and never obtain a second GUI-thread session.

The recipe format does not expose arbitrary SCPI, Python expressions, imports, shell commands, or private/dotted attribute access. Session and transport lifecycle methods (`connect`, `disconnect`, `ensure_connected`, `configure_session`, `temporary_timeout`) and `probe_scpi_query` are explicitly unavailable to recipes. JSON configuration mappings are converted to the corresponding validated public config dataclasses before method-signature preflight.

Pause/cancel are cooperative. Delay and retry waits are interruptible; paused wall time does not consume a Delay budget. A public driver method already executing is not forcibly interrupted from another thread, because that would violate worker/session ownership. Its normal driver timeout/cancellation behavior remains the bound for that operation.

This engine is the reuse boundary for later features: A16 consumes recipe-produced values/results for pass/fail evaluation, A18 consumes recipe/result artifacts plus the A16 decision for evidence bundles, and A25 can reuse the same schema and sequencer without Qt.

## A16 pass/fail evaluation boundary

`dpo4000_utils.rules` is also framework-neutral, but unlike A15 it owns **no instrument lifecycle at all**. It accepts a caller-provided mapping of values and returns a deterministic decision tree.

Supported scalar rules include:

- `>` / `>=` / `<` / `<=`;
- exact numeric `==` / `!=`;
- inclusive `inside [low, high]` and complementary `outside`;
- `abs_delta<=` against a reference/tolerance;
- `rel_delta<=`, with a zero reference producing `INVALID`.

Logical composition uses three-state `AND` / `OR` / `NOT` semantics. Missing, non-numeric, NaN, Inf, or otherwise unusable inputs produce `INVALID`; such inputs never silently become `PASS`.

A16 result records contain stable rule IDs, the actual numeric value when available, the expected operator/limit mapping, one UTC timestamp shared by the evaluation tree, a reason string, and the nested child results. Rule IDs must be unique and the rule document is bounded by node/depth limits.

`recipe_result_values()` is the A15→A16 adapter. Every completed A15 step is addressable by `step.<index>` and `step.<name>`. A unique step name is also exposed directly, and dataclass/mapping results are flattened with dot-separated keys. Duplicate step names are deliberately not promoted to ambiguous direct keys.

A16 does not evaluate Python expressions, import modules, execute shell commands, own SCPI, or implement sequencing/branching. Sequencing remains A15's responsibility; later branching can consume A16 outcomes without moving control flow into the rule engine.

In DPO4000 Desk, A16 evaluation runs only after an A15 recipe reaches `COMPLETED`. It executes in the GUI-side continuation because the rule engine is local and deterministic; no second worker action or VISA session is created. Failed/cancelled recipes are not reinterpreted as pass/fail rule outcomes.

## Driver boundary rule

Desktop GUI code must not:

- access `DPO4000Scope.scope` directly;
- issue SCPI through the underlying PyVISA object;
- parse hardcopy byte streams;
- implement setup JSON restore logic;
- implement waveform acquisition/CSV transfer logic;
- configure raw VISA timeout or line termination itself.

The GUI owns presentation/orchestration concerns: dialogs, destination folders, generated filenames, preview rendering, widget state, preferences, logging, keyboard shortcuts, Automation/Logger/Recipe state projection, rule-set editing/result projection, and asynchronous worker dispatch.

`tests/test_gui_driver_boundary.py` protects the public-driver boundary. `tests/test_a14_trigger_gui_contract.py` additionally locks the composed Trigger page to the same rule and verifies the A14 widget/enabled-state contract. A15 adds recipe boundary/integration tests that protect worker-owned scope execution, preflight-before-I/O, canonical navigation, pause timing, and denied transport/raw-probe methods. A16 adds rule-operator, invalid-input, logical-composition, schema, recipe-context, and GUI-contract tests. `tests/test_gui_qt_composition_architecture.py` protects the v0.8 composition boundary: shallow launch MRO, one approved legacy adapter, explicit controller dependencies, and no raw VISA/SCPI ownership in the composition layer. `tests/test_async_scope_action_contract.py` continues to protect the asynchronous state machines introduced in v0.7.

## Session lifecycle

`DPO4000Scope` accepts `timeout_ms`, `read_termination`, and `write_termination` settings. `ConnectionMixin.connect()` applies them before the initial identity query. Runtime updates use the public `configure_session()` method; GUI worker code does not mutate the raw VISA resource.

The feature runtime creates one `PersistentScopeSession` lazily. Its dedicated worker thread creates, uses, reconnects, and closes the retained `DPO4054` on that same thread. Requests are serialized using Qt queued connections and completion is delivered back to the GUI through callbacks/signals. v0.8 routes all feature-surface `_run_action()` calls through the composed `ScopeDispatchController` before they enter that runtime.

There is deliberately **no nested `QEventLoop` wait** in the production scope path. Scope submission returns immediately. Code that needs a result supplies `on_success` / `on_error` continuations. The A14 Trigger page follows this rule for trigger and B-trigger readback updates. The A15 Recipe page uses the same continuation boundary; per-step progress is projected back to Qt through signals while execution remains on the scope worker. A16 consumes the completed `RecipeResult` in that continuation and performs no instrument call.

`Keep session` defaults to enabled. When disabled for backend compatibility, the same worker/session architecture is used but the retained scope is closed after the operation. Transport errors invalidate the session so a later retry reconnects lazily.

`scope_session()` remains a supported framework-neutral short-lived lifecycle helper for scripts and non-retained use cases; it is not the normal launched-GUI lifecycle.

## Page lifecycle

The canonical production layout exposes eleven pages: Connection, Channels, Measurement, Trigger, Acquisition, Automation, Recipe, Logger, File, Display, and Log. `PageController.ensure_built()` owns the production lazy-build trigger and delegates into the compatibility surface. Migrated builders such as Connection, Trigger, and Recipe are selected by `ComposedFeatureSurface`, so new page behavior is composition-owned without adding another historical window inheritance layer. `PageController.select()` owns navigation state and delegates projection into the current feature surface.

Recipe is inserted between Automation and Logger. Existing shortcuts remain stable; Recipe uses `Ctrl+Shift+6` so the historical Logger/File/Display/Log shortcuts do not move. A16 extends this same Recipe page rather than adding another top-level page, because rules are attached to completed recipe values/results.

This keeps the production page registry explicit while mature page widget implementations are being retired incrementally.

## Coherent parameter refresh

Connection refresh is staged as Core → REF → BUS for fault isolation and fast Core-state projection. The same worker-owned scope connection is retained across the stages. A BUS/REF capability failure therefore does not force a new connection or erase an already successful Core snapshot.

## Shutdown and cancellation

The composed top-level window delegates shutdown to `LifecycleController`, which closes the compatibility feature surface. The mature close chain stops Automation and Logger activity, marks cooperative cancellations, closes the retained instrument on its owning worker thread, and tears down the worker safely. Threads are not forcibly terminated while VISA code is running; the configured driver timeout remains the upper bound for a backend operation that cannot cooperate sooner.

Automation fresh-Single workflows additionally use cancellation events and bounded acquisition timeouts. A15 Recipe cancellation uses its own cooperative event/checkpoint path within the serialized worker action. A16 has no asynchronous activity of its own and therefore adds no shutdown/session behavior.

## Driver calls used by DPO4000 Desk

Representative public operations include:

- `query_identity()`;
- `configure_session()`;
- `get_channel_label()` / `set_channel_label()`;
- `get_channel_configuration()` / `configure_channel()`;
- `get_math_configuration()` / `configure_math()`;
- `get_all_measurement_setups()` / `add_measurement()` / `disable_measurement()`;
- `get_trigger_level()` / `set_trigger_level()` / `configure_edge_trigger()`;
- `get_trigger_configuration()` / `configure_trigger()`;
- `get_trigger_holdoff()` / `set_trigger_holdoff()`;
- `get_sequence_trigger_configuration()` / `configure_sequence_trigger()`;
- `get_acquisition_setup()` / `configure_acquisition()`;
- `get_display_settings()` / `apply_display_settings()`;
- `get_reference_configuration()` / `configure_reference()`;
- `get_bus_configuration()` / `configure_bus()`;
- `get_decoded_bus_capability()`;
- `save_image_path()`;
- `save_all_channels_to_single_csv()`;
- `save_scope_settings()` / `apply_scope_settings()`.

`probe_scpi_query()` is a driver-level qualification utility rather than a normal GUI or recipe operation. It temporarily caps the active VISA timeout, treats a timeout as unsupported only after recovery/health validation, and restores the prior timeout exactly. This prevents exploratory capability checks from inheriting the normal long operational timeout.

Decoded BUS transaction extraction is capability-gated until hardware qualification; no undocumented command is owned by the GUI.

## GUI support package

`dpo4000_utils.gui` remains a framework-neutral support namespace for filename generation, persistent preferences, and packaged assets. It is not an alternate frontend and contains no Tk implementation.

## Migration policy

New production behavior belongs in the composition controllers/services or framework-neutral driver/runtime modules. New inheritance layers must not be added to the production launch path. Legacy `*_window.py` modules may be changed only to preserve compatibility or while extracting a feature behind the adapter. The adapter itself is an explicit migration seam and must not grow raw transport or SCPI responsibilities.
