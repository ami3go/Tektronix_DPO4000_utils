# Logger Tab Canonical Layout

Status: **normative UI task specification**  
Target planning version: **v0.6.11**

This document defines the canonical DPO4000 Desk **Logger** page layout. It complements `logger-tab-plan.md` and must be used by the implementation rather than treating the Logger UI as a generic settings form.

## 1. Navigation

Logger is inserted after Automation and before File:

```text
Connection | Channels | Measurement | Trigger | Acquisition | Automation | Logger | File | Display | Log
```

## 2. Design goals

- Make Start/Stop state and data health visible at a glance.
- Keep source selection separate from output format.
- Hide irrelevant mode-specific controls.
- Show actual transfer/logging throughput, not theoretical scope sample rate.
- Make queue pressure, skipped records, reconnects and disk risk impossible to miss.
- Make 24/7 operation configurable without making simple measurement logging difficult.

## 3. Page structure

The Logger page uses a scrollable vertical layout with a compact profile toolbar and seven logical areas.

```text
Logger
 ├─ Profile toolbar + live recipe summary
 ├─ Status & Control
 ├─ Sources
 ├─ Acquisition / Rate
 ├─ Output & Rotation
 ├─ Retention
 ├─ Reliability & Buffering
 └─ Current Run / Health / Report
```

Cards should use the same visual language as existing DPO4000 Desk cards.

## 4. Canonical wireframe

```text
┌─────────────────────────────────────────────────────────────────────┐
│ LOGGER                                                              │
│ Profile: [ Long burn-in ▼ ] [New] [Save] [Save As] [Import/Export] │
│                                                                     │
│ Recipe: Log CH1 + CH2 + MATH and MEAS1..4 as Binary.               │
│         Rotate every 1 GB or 1 h. Reconnect automatically.         │
├─────────────────────────────────────────────────────────────────────┤
│ STATUS & CONTROL                                                    │
│                                                                     │
│ State:          ● Idle                                              │
│ Mode:           Mixed record                                        │
│ Started:        --                                                  │
│ Elapsed:        --                                                  │
│ Records:        0            Skipped/Dropped: 0                     │
│ Errors:         0            Reconnects: 0                          │
│                                                                     │
│ [ Run once ]           [ Start ]   [ Pause ]   [ Stop ]             │
├─────────────────────────────────────────────────────────────────────┤
│ SOURCES                                                             │
│                                                                     │
│ Waveforms                                                           │
│ [✓] CH1  [✓] CH2  [ ] CH3  [ ] CH4  [✓] MATH                     │
│                                                                     │
│ Measurements                                                        │
│ [✓] MEAS1 [✓] MEAS2 [✓] MEAS3 [✓] MEAS4                           │
│ [ ] MEAS5 [ ] MEAS6 [ ] MEAS7 [ ] MEAS8                           │
│                                                                     │
│ Decoded buses                                                       │
│ [ ] BUS1 I2C   [ ] BUS2 SPI   [unsupported BUS3/4 hidden]          │
│                                                                     │
│ Source status: CH1 100k pts · CH2 100k pts · MATH 100k pts         │
├─────────────────────────────────────────────────────────────────────┤
│ ACQUISITION / RATE                                                  │
│                                                                     │
│ Logger mode:      [ Mixed record ▼ ]                                │
│ Acquisition:      [ Continuous acquisitions ▼ ]                     │
│ Record interval:  [ As fast as safely possible ▼ ]                  │
│                    or Every [ 1.0 ] [ seconds ▼ ]                   │
│                                                                     │
│ Waveform points:   [ Current record length ▼ ]                      │
│ Measurement poll:  [ 500 ] ms                                      │
│ BUS extraction:    [ Per completed acquisition ▼ ]                  │
│                                                                     │
│ [ ] Stop after [ 10000 ] records                                   │
│ [ ] Stop after [ 24 ] [ hours ▼ ]                                  │
├─────────────────────────────────────────────────────────────────────┤
│ OUTPUT & ROTATION                                                   │
│                                                                     │
│ Format:         ( ) CSV     (●) Binary DPO4LOG                      │
│ Output folder:  [/data/scope/logger/________________] [Folder]      │
│ Run subfolder:  [✓] 2026-09-01_113800_Long-burn-in                 │
│                                                                     │
│ Rotate when:                                                        │
│ [✓] file reaches [ 1 ] GB                                          │
│ [✓] segment reaches [ 1 ] hour                                     │
│ [ ] records reach [ 1000 ]                                         │
│ [ ] at daily boundary                                               │
│                                                                     │
│ File example: burnin_20260901_113800_0001.dpo4log                  │
├─────────────────────────────────────────────────────────────────────┤
│ RETENTION                                                           │
│                                                                     │
│ [ ] Keep last [ 100 ] segments                                     │
│ [✓] Maximum Logger storage [ 20 ] GB                               │
│ [✓] Delete completed segments older than [ 14 ] days               │
│ [✓] Stop if free disk below [ 2 ] GB                               │
│                                                                     │
│ Current free disk: 184 GB                                          │
├─────────────────────────────────────────────────────────────────────┤
│ RELIABILITY & BUFFERING                                             │
│                                                                     │
│ [✓] Keep VISA session                                              │
│ [✓] Automatic reconnect                                            │
│ Retry count:          [ 3 ]                                        │
│ Reconnect backoff:    [ 2 ] s                                      │
│ Stop after failures:  [ 10 ]                                       │
│                                                                     │
│ Queue capacity:       [ 8 ] records                                │
│ Queue overflow:       [ Pause producer / skip if unavoidable ▼ ]   │
│ Writer flush:         [ Every 5 s ▼ ]                              │
│                                                                     │
│ [✓] Stop on writer/disk error                                      │
│ [✓] Preserve completed frames after abnormal exit                  │
├─────────────────────────────────────────────────────────────────────┤
│ CURRENT RUN / HEALTH                                                │
│                                                                     │
│ Effective record rate:   2.4 records/s                             │
│ Waveform throughput:     4.8 Mpoints/s                             │
│ Scope payload:           9.6 MB/s                                  │
│ Disk write:              8.3 MB/s                                  │
│                                                                     │
│ Queue: 2 / 8       Peak: 5 / 8                                    │
│ Segment: 437 MB / 1 GB                                              │
│ Total written: 8.6 GB                                              │
│                                                                     │
│ Last record: #002731 ✓  11:38:12.443   405 ms                     │
│ Last error:  --                                                    │
│                                                                     │
│ [ Open run folder ] [ Open report ] [ Inspect current segment ]    │
└─────────────────────────────────────────────────────────────────────┘
```

## 5. Profile toolbar

Always visible above the cards.

Controls:

- Profile combo.
- New.
- Save.
- Save As.
- Import JSON.
- Export JSON.

A profile saves Logger configuration, not active runtime state.

When a run is active, profile-changing controls are disabled.

## 6. Live recipe summary

Below the profile toolbar, show a human-readable summary derived from the current configuration.

Examples:

```text
Log MEAS1..MEAS8 every 500 ms to CSV. Rotate hourly. Stop after 24 hours.
```

```text
Log CH1 + CH2 + MATH after each completed acquisition to Binary DPO4LOG.
Rotate at 1 GB or 1 hour. Reconnect automatically.
```

```text
Log CH1..CH4 + MATH + MEAS1..4 + BUS1 under one acquisition ID.
Run as fast as safely possible with an 8-record writer queue.
```

The recipe updates immediately while Idle and is frozen to the active job snapshot after Start.

## 7. Status & Control card

Always expanded and always visible near the top.

### Fields

- State: Idle / Starting / Running / Paused / Recovering / Stopping / Failed.
- Active mode.
- Started timestamp.
- Elapsed duration.
- produced records.
- written records.
- skipped/dropped records.
- errors.
- reconnects.

### Buttons

- **Run once** — perform one complete Logger record cycle without starting recurrence.
- **Start**.
- **Pause / Resume**.
- **Stop**.

`Run once` is especially important for validating source compatibility, output permissions and binary/CSV writing before unattended operation.

## 8. Sources card

### 8.1 Waveforms

Checkboxes:

```text
CH1 CH2 CH3 CH4 MATH
```

Only enabled/available sources should be selectable after a successful scope connection check. The UI may offer `Select enabled` as a utility button.

MATH is treated as a waveform source and uses the existing structured waveform API.

### 8.2 Measurements

Checkboxes:

```text
MEAS1 ... MEAS8
```

Show concise metadata beside enabled measurement slots if available:

```text
MEAS1  RMS(CH1)
MEAS2  FREQUENCY(CH2)
```

### 8.3 BUS decoders

Show only slots reported by the scope.

Example:

```text
BUS1  I2C  "Control"
BUS2  SPI  "EEPROM"
```

Until decoded-event API support is hardware-qualified, the BUS logging checkboxes must be disabled with a tooltip explaining that decoder configuration is supported but decoded-event extraction is not yet qualified.

### 8.4 Source compatibility status

Show warnings inline, not in modal dialogs:

- different waveform record lengths;
- unsupported MATH transfer;
- unavailable measurement slot;
- BUS decoder extraction unsupported;
- no persistent source selected.

Start remains disabled while the active configuration is invalid.

## 9. Acquisition / Rate card

### Logger mode

Use one combo/radio group:

- **Waveform records**
- **Measurements**
- **BUS events**
- **Mixed record**

The mode changes visibility of subordinate controls.

### Waveform controls

Visible for Waveform or Mixed:

- Continuous acquisitions / Single-save-rearm.
- Current full record or explicit point count/range.
- Desired record interval.
- `As fast as safely possible`.

### Measurement controls

Visible for Measurements or Mixed:

- poll interval;
- timestamp policy;
- invalid-value handling display.

### BUS controls

Visible for BUS or Mixed:

- extraction policy;
- acquisition association;
- BUS slot metadata.

### Run limits

Always available:

- maximum records;
- maximum duration;
- optional absolute stop time later.

## 10. Output & Rotation card

### Format

Primary choices:

```text
CSV
Binary DPO4LOG
```

For Mixed mode, a future advanced option may allow both simultaneously, but v1 should prefer one primary sink to make throughput deterministic.

### CSV-specific options

When CSV is selected, show:

- waveform layout policy;
- measurement column policy;
- BUS normalized columns;
- flush interval.

### Binary-specific options

When Binary is selected, show:

- DPO4LOG schema version read-only;
- checksum enabled read-only for v1;
- optional compression only if later proven not to threaten acquisition throughput.

Do not add compression to the first binary implementation.

### Rotation

Checkbox + value controls:

- max size;
- max duration;
- max records;
- daily boundary.

The earliest enabled threshold wins.

## 11. Retention card

Collapsed by default after configuration is stable.

Controls:

- maximum files/segments;
- maximum Logger GB;
- delete older than N days;
- minimum free disk stop threshold.

Show current free space and estimated remaining runtime when a meaningful average write rate is available.

Example:

```text
Free: 184 GB · Current rate: 8.3 MB/s · Estimated space: ~6 h 9 min
```

Estimate must be clearly marked as approximate.

## 12. Reliability & Buffering card

Collapsed by default, but any warning promotes the card header visually.

Controls:

- Keep VISA session.
- Automatic reconnect.
- retry count.
- reconnect delay/backoff.
- stop after consecutive failures.
- queue capacity.
- queue overflow policy.
- writer flush policy.
- stop on writer/disk error.

### Queue visualization

When running, show a compact queue meter:

```text
Writer queue  [█████-----] 5 / 10
```

Threshold behavior:

- < 60% normal;
- 60–80% warning state;
- > 80% critical state;
- full queue invokes configured overflow policy.

Do not rely on color alone; include numeric text/status labels.

## 13. Current Run / Health area

Always expanded while Running or Recovering.

### Throughput

Show moving averages and totals:

- records/s;
- waveform points/s;
- scope transfer bytes/s;
- disk bytes/s.

These are Logger throughput values, **not oscilloscope sample rate**.

### Queue / writer

- current queue depth;
- peak queue depth;
- records produced;
- records written;
- records skipped/dropped;
- current segment number and size;
- total bytes written.

### Connection

- resource;
- Keep session state;
- last successful scope operation;
- reconnect count;
- last reconnect timestamp.

### Last activity

Show one concise line:

```text
#002731 ✓ 11:38:12.443 · CH1, CH2, MATH + MEAS1..4 · 405 ms
```

On partial record:

```text
#002732 PARTIAL · waveforms saved; BUS1 read failed · 911 ms
```

### Actions

- Open run folder.
- Open report.
- Inspect current segment.

`Inspect current segment` must never modify the active file.

## 14. Dynamic layouts by mode

### 14.1 Measurements only

Show minimal form:

```text
Sources
  MEAS1..MEAS8

Rate
  Every [500] ms

Output
  CSV
  Rotate hourly

Limits
  24 h
```

Hide waveform transfer and BUS controls entirely.

### 14.2 Waveform records

```text
Sources
  CH1 CH2 MATH

Acquisition
  Continuous
  As fast as safely possible
  Current record length

Output
  Binary DPO4LOG
  Rotate 1 GB / 1 h
```

Hide measurement/BUS polling fields.

### 14.3 BUS events

```text
Sources
  BUS1 I2C
  BUS2 SPI

Acquisition association
  Per completed acquisition

Output
  CSV or Binary
```

Hide waveform controls.

### 14.4 Mixed record

Show all selected source groups but keep advanced controls collapsible. Each completed record gets one acquisition ID.

## 15. Running-state locking

After Start:

Disable changes to:

- profile;
- source selection;
- mode;
- record range;
- output format;
- output root;
- rotation thresholds;
- queue size;
- reconnect policy.

Keep available:

- Pause/Resume;
- Stop;
- Open folder/report;
- local UI navigation;
- non-scope viewing actions.

The active job uses an immutable configuration snapshot.

## 16. Validation behavior

Use inline validation and a compact summary near Start.

Examples:

```text
Cannot start: no Logger source selected.
```

```text
Cannot start: output folder is not writable.
```

```text
Cannot start BUS logging: decoded BUS event API is unavailable for this scope/driver.
```

```text
Warning: CSV waveform logging at 10M points may be slower than acquisition; Binary is recommended.
```

Warnings may allow Start; errors do not.

## 17. Accessibility and bench-use requirements

- Controls must remain usable at 100–200% display scaling.
- Status must not depend on color alone.
- Start and Stop must be visually distinct and separated enough to avoid accidental clicks.
- Stop remains visible without scrolling while Logger runs where practical; if not, use a persistent running control strip/header.
- Tooltips explain `As fast as safely possible`, queue overflow, Binary DPO4LOG, retention and reconnect semantics.
- Keyboard focus order follows top-to-bottom workflow.

## 18. UI acceptance criteria

- Logger appears between Automation and File.
- Page navigation remains correct with ten pages.
- All source groups are discoverable without leaving Logger.
- Irrelevant mode fields are hidden, not merely disabled en masse.
- `Run once` validates a full source-to-file cycle.
- Start cannot proceed with no valid source or invalid output path.
- Active configuration is frozen during a run.
- Queue depth and dropped/skipped counters are visible while running.
- Effective record rate and storage throughput are visible and correctly labelled.
- Automatic reconnect state is visible when Recovering.
- Disk/retention warnings are visible before data loss.
- Stop remains available and safely drains/closes the writer.
- Measurement-only mode is simple enough to configure without touching waveform/BUS options.
- BUS logging is visibly unavailable until the required driver API exists rather than silently producing empty files.
