# Automation Tab Canonical UI Layout

Status: **normative implementation task requirement**  
Planning version: **v0.6.10**

This document defines the canonical user-interface layout for the DPO4000 Desk Automation page. It is part of the Automation implementation task and must be used together with:

- `docs/automation-tab-plan.md`
- `docs/automation-feature-backlog.md`

The goal is to keep the page understandable during bench use while still exposing the reliability controls required for unattended and 24/7 operation.

## 1. Top-level page placement

Insert **Automation** after **Acquisition** and before **File**.

```text
Connection | Channels | Measurement | Trigger | Acquisition | Automation | File | Display | Log
```

Automation is one scrollable page using the same visual language as the existing DPO4000 Desk controls.

## 2. Core UX rule

Do not expose A1..A12 as twelve separate automation modes.

Use four operator-facing modes:

1. **Periodic**
2. **Scope Trigger**
3. **Measurement Condition**
4. **Burst**

The selected **Actions** determine what each event produces.

Feature mapping:

| Requirement | UI representation |
| --- | --- |
| A1 Periodic Image | Periodic + Save Image |
| A2 Image on Trigger | Scope Trigger + Save Image |
| A3 Image + CSV on Trigger | Scope Trigger + Save Image + Save CSV |
| A4 Timed waveform logging | Periodic + Save CSV |
| A5 Measurement logger | Periodic + Log MEAS1..MEAS8 |
| A6 Conditional capture | Measurement Condition + selected actions |
| A7 Burst capture | Burst + selected actions |
| A8 Run duration/count limits | Run Limits card |
| A9 File retention | Output & Retention card |
| A10 Automation profiles | Profile toolbar |
| A11 Automatic reconnect | Reliability card |
| A12 Automation report | Current Run / Report area |

This separation prevents the UI from becoming a list of nearly-duplicate workflows.

## 3. Canonical page structure

The page shall contain:

1. **Profile toolbar**
2. **Live recipe summary**
3. **Status & Control card**
4. **Automation Mode card**
5. **Actions card**
6. **Run Limits card**
7. **Output & Retention card**
8. **Reliability card**
9. **Current Run / Report card**

The six main configuration/control cards are:

- Status & Control
- Automation Mode
- Actions
- Run Limits
- Output & Retention
- Reliability

The profile toolbar and current-run/report area are supporting UI rather than additional configuration cards.

## 4. Canonical layout sketch

```text
┌──────────────────────────────────────────────────────────────┐
│ AUTOMATION                                                   │
│ Profile: [ Burn-in test ▼ ] [New] [Save] [Save As] [JSON]  │
├──────────────────────────────────────────────────────────────┤
│ RECIPE                                                       │
│ Arm Single acquisition. After each completed trigger,        │
│ save Image + CSV and re-arm. Stop after 500 triggers.        │
├──────────────────────────────────────────────────────────────┤
│ STATUS & CONTROL                                             │
│ State:        ● Idle                                         │
│ Mode:         Image + CSV on Trigger                         │
│ Started:      --                                             │
│ Last event:   --                                             │
│ Next event:   --                                             │
│ Captures: 0   Errors: 0   Reconnects: 0   Skipped: 0        │
│                                                              │
│ [ Run once ]        [ Start ]   [ Pause ]   [ Stop ]         │
├──────────────────────────────────────────────────────────────┤
│ AUTOMATION MODE                                              │
│ (●) Periodic                                                 │
│ ( ) Scope Trigger                                            │
│ ( ) Measurement Condition                                    │
│ ( ) Burst                                                    │
│                                                              │
│ <mode-specific controls shown here>                          │
├──────────────────────────────────────────────────────────────┤
│ ACTIONS                                                      │
│ [✓] Save Image                                               │
│ [✓] Save CSV                                                 │
│ [ ] Log MEAS1..MEAS8                                         │
│ [ ] Save scope settings                                      │
│ [ ] Save event JSON manifest                                 │
│ [ ] Refresh screen preview                                   │
├──────────────────────────────────────────────────────────────┤
│ RUN LIMITS                                                   │
│ [✓] Maximum captures        [ 1000 ]                         │
│ [ ] Maximum run duration    [ 8 ] [ hours ▼ ]                │
│ [ ] Stop at date/time       [ YYYY-MM-DD HH:MM ]             │
├──────────────────────────────────────────────────────────────┤
│ OUTPUT & RETENTION                                           │
│ Output folder: /data/scope-tests/                            │
│ [✓] Create run subfolder                                     │
│ Filename: [scope]_[timestamp]_[sequence]                     │
│ Example: scope_20260901_113812_0027.png                      │
│                                                              │
│ [ ] Keep last              [ 1000 ] files                    │
│ [✓] Maximum storage        [ 20 ] GB                         │
│ [✓] Delete files older than [ 14 ] days                      │
│ Free disk: 184 GB                                            │
├──────────────────────────────────────────────────────────────┤
│ RELIABILITY                                                  │
│ Retry failed event:           [ 2 ] times                    │
│ Retry delay:                  [ 1 ] seconds                  │
│ Stop after consecutive errors:[ 5 ]                          │
│ [✓] Automatically reconnect VISA                             │
│ [✓] Skip event if previous event is still running            │
│ [✓] Stop if free disk below [ 2 ] GB                         │
├──────────────────────────────────────────────────────────────┤
│ CURRENT RUN / REPORT                                         │
│ Progress: 27 / 1000                                          │
│ ███░░░░░░░░░░░░░░░░                                         │
│ Last: 11:38:12  Image + CSV    ✓  1.46 s                    │
│ Next: 11:38:22                                                │
│ [ Open run folder ]   [ Open report ]                        │
└──────────────────────────────────────────────────────────────┘
```

Exact spacing and responsive sizing may follow the existing PySide6 style, but the information hierarchy and grouping above are required.

## 5. Profile toolbar

The top row shall contain:

```text
Profile: [ profile name ▼ ] [New] [Save] [Save As] [Import/Export JSON]
```

Requirements:

- Profile controls remain visible without scrolling when practical.
- Selecting a profile loads configuration only; it must not start automation.
- Saving a profile snapshots the current editable configuration.
- Runtime counters/state are never stored as configuration.
- Loading a profile while automation is running is disabled in v1.

This implements A10 without consuming a large card in the page body.

## 6. Live recipe summary

Directly below the profile toolbar, show a read-only natural-language summary generated from current configuration.

Examples:

### Periodic Image

```text
Every 10 seconds, save Image.
Stop after 100 captures or 2 hours.
Reconnect automatically after communication failure.
```

### Image + CSV on Trigger

```text
Arm Single acquisition.
After each completed trigger, save Image + CSV and re-arm.
Stop after 500 triggers.
```

### Conditional capture

```text
Poll MEAS1 every 500 ms.
If MEAS1 > 10 V for 3 consecutive samples, save Image + CSV.
Allow one capture every 30 seconds.
```

The recipe must update immediately when editable configuration changes.

Purpose:

- provide a pre-start sanity check;
- expose accidental combinations before unattended operation;
- make complex profiles understandable without opening every card.

## 7. Status & Control card

Always visible near the top of the page.

Fields:

- State: `Idle`, `Starting`, `Running`, `Paused`, `Stopping`, `Failed`.
- Active mode/profile.
- Started at.
- Last event.
- Next event or next poll.
- Successful captures/events.
- Skipped events.
- Failed events.
- Retry count.
- Reconnect count.
- Last error, when present.

Controls:

- **Run once**
- **Start**
- **Pause / Resume**
- **Stop**

Rules:

- `Run once` validates and executes one event without starting the recurring controller.
- `Start` is enabled only when configuration validates.
- `Pause` stops new scheduling/poll progression but never interrupts an already-active VISA transaction mid-command.
- `Stop` is idempotent.
- Buttons shall reflect the controller state machine; do not infer state only from button text.

## 8. Automation Mode card

The mode selector contains exactly the four primary modes in v1/v2 planning:

```text
( ) Periodic
( ) Scope Trigger
( ) Measurement Condition
( ) Burst
```

Only controls relevant to the selected mode are visible.

Do not leave disabled fields for other modes occupying permanent space.

### 8.1 Periodic mode fields

Show:

```text
Interval:      [ 10 ] [seconds/minutes/hours ▼]
Initial delay: [ 0  ] [seconds/minutes/hours ▼]
```

Optional advanced field:

```text
Timing policy: [ fixed interval / after previous completion ▼]
```

Recommended default remains fixed interval with no overlap/backlog; if busy, the missed event is skipped.

### 8.2 Scope Trigger mode fields

Show:

```text
Acquisition behavior: [ Arm Single automatically ▼]
Re-arm after capture:  [✓]
Poll interval:         [500] ms
Trigger timeout:       [ optional ]
```

Do not duplicate trigger source, level, slope, coupling, or mode configuration from the Trigger page.

The Automation page consumes the configured trigger and orchestrates acquisition/capture only.

### 8.3 Measurement Condition mode fields

Show:

```text
Measurement:          [MEAS1 ▼]
Condition:            [> ▼] [10.0]
Second limit:         [only for inside/outside range]
Poll interval:        [500] ms
Consecutive matches:  [3]
Capture cooldown:     [30] seconds
```

Supported conditions:

- greater than
- greater than or equal
- less than
- less than or equal
- inside range
- outside range
- absolute change greater than threshold

The condition card becomes part of the Automation Mode card rather than a permanent separate card.

### 8.4 Burst mode fields

Show:

```text
Events: [20]
Delay:  [2] [seconds ▼]
Acquisition behavior: [Current acquisition / Single-per-event ▼]
```

If `Single-per-event` is selected, the workflow is:

```text
arm -> wait complete -> execute actions -> delay -> re-arm
```

## 9. Actions card

This card specifies what one automation event produces.

Checkboxes:

```text
[ ] Save Image
[ ] Save CSV
[ ] Log MEAS1..MEAS8
[ ] Save scope settings
[ ] Save event JSON manifest
[ ] Refresh screen preview
```

Rules:

- At least one persistent/logging action is required.
- `Refresh screen preview` alone is not sufficient to start unattended automation.
- A3 requires `Save Image` + `Save CSV` to operate on the same completed acquisition before any re-arm operation.
- Measurement logging appends samples into the active run log rather than creating one file per measurement sample by default.

## 10. Run Limits card

Implements A8.

Controls:

```text
[ ] Maximum successful events [100]
[ ] Maximum elapsed duration  [2] [hours ▼]
[ ] Stop at date/time          [date/time]
```

Rules:

- More than one limit may be enabled; the first reached stops the run.
- `Maximum successful events` counts accepted successful automation events, not scheduler ticks.
- Failed/skipped events remain visible in statistics/reporting but do not silently consume the success limit unless a future explicit option says otherwise.
- `0` or blank does not ambiguously mean unlimited; use explicit enable controls.

## 11. Output & Retention card

Implements file output and A9.

Controls:

```text
Output folder: [path........................] [Folder] [Open]
[✓] Create one subfolder per automation run
Filename pattern: [prefix]_[timestamp]_[sequence]
Example: scope_20260901_113812_0027.png

Retention:
[ ] Keep last N files       [1000]
[ ] Maximum storage         [20] GB
[ ] Delete files older than [14] days

Free disk: 184 GB
```

Rules:

- Reuse File-page output configuration where practical rather than duplicating naming logic.
- Show a live filename example.
- Unattended runs never display overwrite dialogs.
- Collisions are resolved deterministically.
- Retention operates only inside the configured automation-owned run root.
- Never delete files currently being written.
- Never follow a path outside the automation root through unsafe traversal/symlink handling.
- Retention runs after successful artifact close/flush, not before.

If multiple retention limits are enabled, enforcement shall reduce usage until all enabled limits are satisfied.

## 12. Reliability card

Implements A11 and general 24/7 policy.

Controls:

```text
Retry failed event:            [2] times
Retry delay:                   [1] seconds
Stop after consecutive errors: [5]
[✓] Automatically reconnect VISA
[✓] Skip event if previous event is still running
[✓] Stop if free disk below [2] GB
```

Recommended defaults:

- retries: `2`
- retry delay: `1 s`
- consecutive failure stop: `5`
- reconnect: enabled
- no overlap / skip busy tick: enabled
- disk guard: enabled for unattended profiles

The card should include concise explanatory tooltips rather than long permanent paragraphs.

## 13. Current Run / Report card

Implements the operator-facing side of A12.

Fields:

- profile name
- mode
- start time
- elapsed time
- successful events
- skipped events
- failed events
- retries
- reconnects
- current disk usage
- last event status/duration
- next scheduled event/poll
- progress against count/duration limit

Controls:

```text
[ Open run folder ] [ Open report ]
```

Optional later control:

```text
[ Export report now ]
```

When automation finishes, this card remains populated until the next run starts or the user clears it.

## 14. Dynamic visibility matrix

| UI field/group | Periodic | Scope Trigger | Measurement Condition | Burst |
| --- | :---: | :---: | :---: | :---: |
| Interval | ✓ |  | Poll only | Delay |
| Initial delay | ✓ | optional | optional | optional |
| Trigger re-arm |  | ✓ |  | if single-per-event |
| Trigger poll interval |  | ✓ |  | if single-per-event |
| Measurement selector | optional for logging |  | ✓ | optional for logging |
| Condition/operator |  |  | ✓ |  |
| Debounce |  |  | ✓ |  |
| Cooldown |  |  | ✓ |  |
| Burst count |  |  |  | ✓ |
| Actions | ✓ | ✓ | ✓ | ✓ |
| Run Limits | ✓ | ✓ | ✓ | ✓ |
| Output & Retention | ✓ | ✓ | ✓ | ✓ |
| Reliability | ✓ | ✓ | ✓ | ✓ |
| Current Run / Report | ✓ | ✓ | ✓ | ✓ |

## 15. UI behavior while running

When automation enters `Running`:

- freeze configuration fields that would mutate the active job;
- keep current status/report fields live;
- keep Pause/Stop available according to controller state;
- keep non-scope navigation usable;
- do not silently apply edits to the active job;
- allow the user to inspect File/Trigger/Measurement pages, but block conflicting writes while an automation scope operation is active through the existing serialization rules.

Recommended v1 behavior is to disable configuration editing for the Automation page until paused/stopped rather than support live mutation.

## 16. Collapsible-card defaults

Recommended defaults on opening Automation:

Expanded:

- Status & Control
- Automation Mode
- Actions
- Current Run / Report while a run exists

Collapsed by default:

- Run Limits
- Output & Retention
- Reliability

When a validation error exists inside a collapsed card, automatically expand that card and focus/highlight the relevant field.

## 17. Validation feedback

Avoid modal dialogs for ordinary configuration mistakes.

Use:

- inline field validation;
- concise error text in the affected card;
- disabled Start button until valid;
- recipe summary updated to show incomplete configuration where useful.

Examples:

```text
Interval must be at least 1 second.
```

```text
Select at least one persistent or logging action.
```

```text
Retention storage limit must be greater than the free-disk stop threshold.
```

Modal error dialogs remain appropriate for unexpected runtime failures that need immediate operator awareness.

## 18. Accessibility and bench-use requirements

- Do not rely on color alone for state; use text plus icon/state marker.
- Controls must remain keyboard reachable.
- Start/Stop controls must not move when mode-specific fields change.
- Avoid horizontally scrolling the main Automation page at normal application sizes.
- Long paths and errors should elide/wrap without forcing the card wider.
- Use existing theme/QSS rather than introducing an Automation-specific visual theme.
- Use clear engineering units next to numeric fields.

## 19. Acceptance criteria for the layout task

The Automation UI implementation is acceptable when:

1. Automation appears between Acquisition and File.
2. A1..A12 map to the four modes + supporting cards exactly as defined above.
3. The page contains the canonical profile toolbar, recipe summary, six configuration/control cards, and Current Run / Report area.
4. Switching modes hides irrelevant fields rather than leaving a large disabled form.
5. Start/Run once are disabled for invalid configurations.
6. The recipe summary accurately describes the active configuration.
7. The user can configure A1, A3, A4, A5, A6, and A7 without leaving the Automation page except for existing scope setup pages such as Trigger/Measurement configuration.
8. A8, A9, A10, A11, and A12 are visible as supporting capabilities, not automation modes.
9. A3 visibly indicates same-acquisition Image + CSV semantics.
10. Retention and reconnect options are accessible without cluttering the default basic workflow.
11. Running state freezes job-defining fields and keeps status/Stop available.
12. No Automation widget issues raw SCPI; the UI binds only to controller/model/service APIs.
13. Existing DPO4000 Desk theme, collapsible-card behavior, lazy page construction, and keyboard navigation remain consistent.
14. Qt runtime tests cover mode switching, dynamic visibility, recipe generation, validation, start/stop state, and collapsed-card error reveal.

## 20. Implementation note

The layout is intentionally **configuration-driven**:

```text
Mode + Actions + Limits + Retention + Reliability = AutomationJob
```

The UI must build an immutable `AutomationJob` snapshot when `Run once` or `Start` is selected. The controller/executor must not read live widget values during a running job.

This layout is the canonical UI requirement for the Automation implementation task unless a later versioned design explicitly supersedes it.
