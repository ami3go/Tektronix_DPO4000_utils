# Automation Tab Implementation Plan

Status: **planned, not implemented**  
Target planning version: **v0.6.8**

## 1. Objective

Add a dedicated **Automation** page to DPO4000 Desk for unattended and repeated oscilloscope workflows while preserving the repository architecture:

- `dpo4000_utils` owns Tektronix communication, SCPI behavior, validation, acquisition, hardcopy, waveform, and settings operations.
- The PySide6 GUI remains a wrapper/orchestrator.
- Automation must not add a second VISA/SCPI implementation inside GUI code.
- All scope access must remain serialized and must use the existing public driver API and worker/session infrastructure.

The initial automation feature should be safe for long-running lab use and should fail predictably rather than silently overlapping, overwriting data, or leaving the instrument in an unknown state.

## 2. Current repository capabilities that should be reused

The current GUI already provides most building blocks needed by automation:

- Public driver object: `DPO4054` / `DPO4000Scope`.
- Scope operation gateway: `_run_action(...)`.
- Optional worker-owned persistent VISA session: `PersistentScopeSession`.
- Transient in-memory screen preview: `read_screen_png()`.
- Persistent PNG capture: `save_image_path(...)`.
- Full-record enabled-channel CSV export: `save_all_channels_to_single_csv(...)`.
- JSON scope setup save/restore.
- Existing output directory, prefix, basename, and timestamp settings.
- Existing Run / Stop / Single / Force acquisition controls.
- Existing operation-active state and transport-error handling.

Automation should compose these capabilities rather than duplicate them.

## 3. Proposed top-level UI placement

Insert **Automation** after **Acquisition** and before **File**.

Proposed page order:

1. Connection
2. Channels
3. Measurement
4. Trigger
5. Acquisition
6. Automation
7. File
8. Display
9. Log

This keeps the workflow logical: configure the scope, configure acquisition, configure automation, then configure output files.

The page-index constants and `Ctrl+1` ... `Ctrl+9` navigation must be updated together. Avoid hard-coded page indices outside the central page-definition module.

## 4. Automation tab UI

The page should use the same scrollable/collapsible card pattern as the existing controls.

### 4.1 Automation status card

Always visible at the top.

Fields:

- State: `Idle`, `Starting`, `Running`, `Paused`, `Stopping`, `Failed`.
- Mode.
- Started at.
- Last run.
- Next run / next poll.
- Successful runs.
- Skipped runs.
- Failed runs.
- Consecutive failures.
- Last error.

Controls:

- **Start**
- **Pause / Resume**
- **Stop**
- **Run once**

`Run once` must execute the currently selected automation action without enabling the recurring scheduler. This is important for validating file paths and scope behavior before unattended operation.

### 4.2 Automation mode card

Initial modes, in implementation order:

1. **Periodic capture** — production target for phase 1.
2. **Capture after scope trigger/acquisition completes** — phase 2.
3. **Measurement condition** — phase 3.
4. **Timed sequence / burst** — phase 3.

#### Periodic capture

Inputs:

- Interval value.
- Unit: seconds / minutes / hours.
- Optional initial delay.
- Optional maximum run count.
- Optional maximum duration.

Recommended minimum interval for v1: **1 second**. The scheduler should reject intervals that are shorter than the selected operation can realistically complete.

#### Trigger-complete capture

Purpose: save artifacts only after the oscilloscope has completed a triggered/single acquisition.

Important architecture rule: the GUI must not embed raw trigger-state SCPI. Add a public driver method, for example:

- `get_trigger_state()` or
- `get_acquisition_state()` / `is_acquisition_complete()`

The exact public API and SCPI query must be verified against the supported DPO4000 hardware/manual and real hardware before this mode is enabled.

Suggested behavior:

- Use the trigger configuration already present on the Trigger page; do not duplicate trigger source/level/slope controls in Automation.
- Optionally issue `Single` when automation starts.
- Poll a validated public driver status method at a conservative interval.
- Detect a state transition, not merely a static state, so one trigger creates one capture.
- Capture requested artifacts.
- Optionally re-arm another single acquisition.

Default poll interval should start conservatively, e.g. 500 ms, and be hardware-qualified before allowing lower values.

#### Measurement condition

Examples:

- MEAS1 > threshold
- MEAS2 < threshold
- value outside `[low, high]`
- value inside `[low, high]`
- absolute delta from previous value > threshold

This mode should use public measurement-read APIs only.

Required controls:

- Measurement slot.
- Operator.
- Threshold(s).
- Debounce / number of consecutive matches.
- Minimum time between captures.

The cooldown prevents one persistent out-of-limit condition from filling the disk.

#### Timed sequence / burst

Examples:

- Capture 20 images every 2 seconds.
- Capture image + CSV 100 times with 5-second spacing.
- Single -> wait complete -> save artifacts -> rearm, repeated N times.

This can reuse the same scheduler and job model as periodic capture with a finite run count.

## 5. Action card

Allow one automation event to produce one or more artifacts.

Phase-1 actions:

- [ ] Save PNG image
- [ ] Save enabled-channel CSV
- [ ] Save scope settings JSON
- [ ] Refresh on-screen preview after PNG capture

Later actions:

- [ ] Log measurement values to a time-series CSV
- [ ] Save a combined run manifest (`.json`)
- [ ] Save image + waveform + settings as one capture bundle

At least one persistent or logging action must be selected before Start is enabled.

### 5.1 Capture bundle

For repeatable engineering evidence, add an optional per-event manifest containing:

- UTC timestamp.
- Local timestamp.
- Sequence number.
- VISA resource.
- Scope IDN.
- automation mode.
- trigger/condition that caused the event.
- generated artifact paths.
- result/error status.
- elapsed operation time.

This gives long-duration runs auditability without parsing the GUI log.

## 6. File behavior

Automation must reuse **File** page output configuration.

Do not show overwrite confirmation dialogs during an unattended automation run.

Required behavior:

- Timestamp should be strongly recommended and automatically enforced if necessary to prevent collisions.
- If a generated path already exists, use a deterministic collision suffix such as `_001`, `_002`, etc., or fail the event according to policy; never silently overwrite unless the user explicitly selected an advanced overwrite policy.
- Optional automation run subfolder, for example:
  - `2026-09-01_103000_run/`
- Optional sequence suffix:
  - `scope_screen_20260901_103001_0001.png`

Recommended default: timestamp + four-digit sequence number.

## 7. Reliability and failure-policy card

Long-running automation needs explicit policy rather than ad-hoc exceptions.

Controls:

- Retry count per event: default `2`.
- Retry delay: default `1 s`.
- Stop after N consecutive failures: default `5`.
- On transport failure:
  - invalidate retained session;
  - reconnect on next retry.
- On validation/protocol failure:
  - do not reconnect blindly;
  - mark the event failed and apply failure policy.
- On busy scope/GUI operation:
  - default **Skip this tick** rather than queue unlimited work.
- Minimum free disk space guard.
- Optional stop automation if free disk falls below threshold.

Recommended v1 missed-interval policy:

**No overlap, no backlog.** If the previous operation is still active when the next timer fires, increment `skipped_runs` and schedule the following normal interval.

This is safer than queueing stale capture requests.

## 8. Scope access serialization

This is a hard requirement.

Automation and manual GUI commands must never communicate with the same instrument concurrently.

Recommended model:

```text
Automation UI
    -> AutomationController
        -> AutomationExecutor
            -> existing serialized GUI scope-action gateway
                -> PersistentScopeSession when enabled
                -> short-lived scope_session otherwise
                    -> public DPO4000 driver API
```

The controller should not create `DPO4054` directly.

### Manual actions while automation is running

Recommended v1 policy:

- Manual read-only/non-scope UI operations remain available.
- Scope-changing manual actions remain available only between automation operations.
- If an automation operation is active, guarded scope buttons stay disabled through the existing operation-active mechanism.
- Starting a new automation while one is already running is rejected.

Do not allow two automation controllers for one window/instrument.

## 9. Scheduler design

Create a dedicated controller rather than putting QTimer logic directly into the window class.

Suggested modules:

```text
dpo4000_utils/gui_qt/automation/
    __init__.py
    models.py
    controller.py
    executor.py
    persistence.py

dpo4000_utils/gui_qt/automation_window.py
```

### 9.1 `models.py`

Dataclasses/enums with no Qt widget dependencies:

- `AutomationMode`
- `AutomationState`
- `AutomationActionConfig`
- `AutomationScheduleConfig`
- `AutomationFailurePolicy`
- `AutomationJob`
- `AutomationEventResult`
- `AutomationStatistics`

Use validated immutable configuration snapshots when Start is pressed. Editing widgets during a run should not silently mutate the active job.

### 9.2 `controller.py`

Responsibilities:

- State machine.
- QTimer scheduling.
- Pause/resume/stop.
- Run-count and duration limits.
- Busy/overlap policy.
- Trigger/condition polling.
- Retry/failure counters.
- Emits structured Qt signals for status/UI updates.

It must not contain Tektronix commands.

### 9.3 `executor.py`

Responsibilities:

- Translate one automation event into calls to existing public driver operations.
- Use the same scope-operation gateway/session policy as manual actions.
- Create artifact paths.
- Return structured results.

It must not implement a second SCPI layer.

### 9.4 `persistence.py`

Persist user automation settings separately from runtime state.

Persist:

- Last selected mode.
- Interval.
- Selected actions.
- failure policy.
- polling interval.
- max count/duration.

Do not auto-resume a previous automation after application restart in v1. Startup should always return to `Idle` for safety.

## 10. State machine

Use an explicit state machine:

```text
Idle
  -> Starting
      -> Running
          -> Paused
              -> Running
          -> Stopping
              -> Idle
          -> Failed
              -> Idle
```

Rules:

- Start validates configuration before entering `Running`.
- Stop is idempotent.
- Closing the GUI requests automation stop before the retained VISA session is shut down.
- A timer callback that arrives after Stop must be ignored using a run/generation token.
- A stale worker completion from a previous run must not restart scheduling.

## 11. Phase plan

### Phase 0 — architecture preparation

- Add Automation page entry and lazy page builder.
- Centralize page indices so inserting a page cannot silently break File/Display/Log references.
- Add automation model/controller skeleton.
- Add status card with disabled Start until configuration is valid.
- No instrument automation yet.

Acceptance:

- Existing manual GUI behavior unchanged.
- `Ctrl+1..9` navigation correct.
- Existing tests remain green.

### Phase 1 — periodic PNG/CSV/settings automation

Implement:

- Periodic mode.
- Image / CSV / settings actions.
- Run once.
- Start / pause / resume / stop.
- Run count and duration limits.
- No-overlap/skip policy.
- Collision-safe names.
- Persist preferences.
- Structured statistics and logging.

This should be the first production-usable milestone.

Acceptance:

- 100+ periodic events in simulation/fake-scope tests with zero overlaps.
- Stop works while idle between events.
- Pause produces no new events.
- Existing manual capture actions still work after stopping automation.
- No file is silently overwritten.
- Transport failure invalidates retained session and follows retry policy.

### Phase 2 — trigger-complete capture

Before UI enablement:

- Add a public, tested driver status API.
- Verify exact DPO4000 state values against real hardware.
- Add fake-driver transition tests.

Implement:

- Single-acquisition arm option.
- Trigger/acquisition state transition detector.
- Capture exactly once per acquisition completion.
- Optional automatic rearm.

Acceptance:

- One physical trigger -> one event.
- A static completed state cannot create duplicate files.
- Rearm works for at least 100 cycles on hardware.
- Disconnect/reconnect cannot accidentally duplicate the previous trigger event.

### Phase 3 — measurement conditions and richer sequences

Implement:

- Measurement threshold conditions.
- Debounce.
- Cooldown.
- Finite burst mode.
- Optional measurement time-series log.
- Optional per-event JSON manifest.

### Phase 4 — long-duration qualification

Run real hardware qualification:

- USB/VISA.
- Ethernet INSTR if supported in the test environment.
- Keep-session OFF.
- Keep-session ON.
- Periodic image only.
- CSV only.
- Image + CSV.
- Trigger/rearm workflow.

Recommended qualification runs:

- 1 hour functional soak.
- 8 hour overnight soak.
- 24 hour stability soak before calling the feature production-ready for unattended lab use.

Capture:

- event count.
- skipped count.
- retry count.
- reconnect count.
- memory growth.
- GUI responsiveness.
- file count/size.
- disk usage.
- final scope connectivity.

## 12. Test strategy

### Unit tests

- Config validation.
- Schedule math.
- state-machine transitions.
- pause/resume semantics.
- stop idempotency.
- run-count limit.
- duration limit.
- sequence numbering.
- path collision handling.
- retry/backoff behavior.
- consecutive-failure stop.
- busy tick skip.
- trigger-state transition detector.
- measurement threshold/debounce/cooldown.

Use a fake clock where possible so tests do not wait on real seconds.

### Qt runtime tests

- Automation page lazy construction.
- Start/Stop button enablement.
- Timer -> executor dispatch.
- UI remains event-responsive.
- Close while automation active.
- Stale completion ignored after Stop.

### Driver boundary tests

Verify the executor calls public driver methods, not raw SCPI writes.

A code-quality test can explicitly forbid new `.write(...)`, `.query(...)`, and raw Tektronix command strings inside the automation GUI/controller modules.

### Real hardware tests

Mark with the existing `hardware` marker and keep opt-in.

For automation, add explicit run limits to every hardware test so CI/bench mistakes cannot create an unbounded capture loop.

## 13. Suggested feature priority

### Must have for v1

1. Periodic PNG capture.
2. Periodic full-record CSV capture.
3. Image + CSV combined event.
4. Start / Pause / Resume / Stop.
5. Run once.
6. Interval + max count + max duration.
7. Collision-safe file naming.
8. No-overlap scheduler.
9. Retry and consecutive-failure stop policy.
10. Automation status/statistics.
11. Persist configuration but never auto-start on application launch.

### High-value next features

12. Capture on completed trigger/single acquisition.
13. Automatic rearm after trigger capture.
14. Measurement limit/event capture.
15. Measurement trend CSV.
16. Per-event manifest.
17. Optional run subfolder.
18. Minimum free disk guard.

### Later / optional

19. Time-of-day start.
20. Daily scheduled runs.
21. Multiple sequential setup profiles.
22. Apply setup JSON at automation start.
23. Restore previous setup at automation end.
24. Export/import automation profiles.
25. Headless automation runner using the same non-GUI automation model/executor.

## 14. Features deliberately excluded from v1

- Running automation after DPO4000 Desk is closed.
- Operating multiple oscilloscopes concurrently from one window.
- Arbitrary user-entered SCPI scripts.
- Cron/service installation.
- Unlimited queue/backlog of missed captures.
- Silent file overwrite.
- Auto-resume after application or PC restart.

These increase safety and support complexity and should only be considered after the in-process scheduler is qualified.

## 15. Repository changes expected during implementation

Likely files to modify:

- `dpo4000_utils/gui_qt/display_window.py`
  - add Automation page and renumber later pages/shortcuts.
- `dpo4000_utils/gui_qt/ui_polish_window.py`
  - final presentation integration if needed.
- `dpo4000_utils/gui_qt/preview_actions_window.py`
  - only if a generic serialized scope-operation hook needs refactoring; do not place scheduler logic here.
- `dpo4000_utils/gui_qt/scope_worker.py`
  - only if a reusable asynchronous/queued execution primitive is needed.
- `dpo4000_utils/gui/preferences.py`
  - persist automation preferences or delegate to dedicated automation persistence.
- `dpo4000_utils/control.py` / `instrument.py`
  - public trigger/acquisition state API when phase 2 is implemented.
- new `dpo4000_utils/gui_qt/automation/*` modules.
- new automation unit/runtime/hardware tests.

## 16. Recommended first implementation slice

The safest first code increment is:

> Add an Automation page with **Periodic** mode, **Image** and **CSV** actions, interval, max run count, `Run once`, `Start`, `Pause`, and `Stop`; use collision-safe timestamped output and a strict no-overlap scheduler through the existing scope action/session path.

Do **not** begin with trigger-state automation. Periodic capture exercises the controller, file workflow, session serialization, retries, and long-run behavior without depending on an additional hardware-specific status API. Once that foundation is stable, trigger-complete capture becomes a contained extension rather than a second scheduler design.
