# Automation Feature Backlog A1-A12

Status: **planned, not implemented**  
Planning increment: **v0.6.9**  
Parent design: [`automation-tab-plan.md`](automation-tab-plan.md)

This document is the authoritative named feature backlog for the DPO4000 Desk Automation tab. It supplements the architecture, scheduler, serialization, failure-policy, and hardware-qualification requirements in the parent plan.

## Feature matrix

| ID | Feature | Required behavior | Priority | Planned delivery |
|---|---|---|---|---|
| A1 | Periodic Image | Save the scope screen every configurable N seconds/minutes/hours. | High | Phase 1 |
| A2 | Image on Trigger | Arm single acquisition, wait for verified trigger/acquisition completion, save one image, optionally re-arm. | High | Phase 2 |
| A3 | Image + CSV on Trigger | Save screenshot and waveform data from the same completed acquisition before any re-arm. | Very high | Phase 2 |
| A4 | Timed waveform logging | Periodically save enabled-channel full-record CSV without screenshots. | High | Phase 1 |
| A5 | Measurement logger | Periodically record MEAS1..MEAS8 values into one time-series CSV. | High | Phase 3 |
| A6 | Conditional capture | Save configured artifacts only when a selected measurement exceeds/falls below or enters/exits configured limits. | Very useful for testing | Phase 3 |
| A7 | Burst capture | Capture N acquisition events/images with configurable delay, with optional image/CSV bundle per event. | Medium | Phase 3 |
| A8 | Run duration/count limits | Stop after configured event count, elapsed duration, or whichever limit is reached first. | Essential | Phase 1 |
| A9 | File retention | Retain by last-N files, maximum storage size, and/or maximum file age; prune safely for unattended 24/7 operation. | Essential for 24/7 use | Phase 1B / Phase 4 qualification |
| A10 | Automation profiles | Save/load complete validated automation configuration as versioned JSON. | High | Phase 3 |
| A11 | Automatic reconnect | Recover after timeout/disconnect by invalidating the failed VISA session and reconnecting through the existing serialized session policy. | Essential for 24/7 | Phase 1 |
| A12 | Automation report | Produce CSV and/or JSON run summary with captures, skips, errors, retries, reconnects, timings, and stop reason. | High | Phase 1B |

## Requirement details and acceptance criteria

### A1 - Periodic Image

Behavior:

- Configurable interval value and unit: seconds, minutes, hours.
- Optional initial delay.
- Save through the existing public image API and File-page naming rules.
- No overlapping capture operations.
- If an interval expires while a previous scope operation is active, apply the configured missed-interval policy; v1 default is **skip, do not queue**.
- `Run once` must validate the configured path and capture flow without starting the recurring scheduler.

Acceptance:

- 100+ scheduled image events in fake-scope tests with zero concurrent instrument operations.
- Files have unique deterministic names.
- Stop/Pause take effect without creating stale queued captures.

### A2 - Image on Trigger

Behavior:

1. Arm a single acquisition through the public driver API.
2. Wait/poll a verified public acquisition/trigger-state API.
3. Detect completion as a state transition, not merely a static state value.
4. Save exactly one image for the completed acquisition.
5. Re-arm only after capture completes when automatic re-arm is enabled.

Hard requirement:

- No raw trigger-state SCPI in GUI/controller code.
- The exact DPO4000 trigger/acquisition-state query and returned values must be verified against supported hardware before this mode is enabled.

Acceptance:

- One physical trigger produces exactly one image.
- A static completed state cannot produce duplicate files.
- 100 trigger/re-arm cycles pass on real hardware before production qualification.

### A3 - Image + CSV on Trigger

This is the primary engineering-evidence workflow.

Behavior:

1. Arm single acquisition.
2. Wait for acquisition completion.
3. Freeze the automation event identity/sequence number.
4. Save the scope image.
5. Read/export enabled-channel waveform data **before any re-arm**.
6. Record both artifacts as belonging to the same automation event.
7. Re-arm only after both artifacts are successfully captured or the event failure policy is resolved.

The screenshot and waveform must represent the same completed acquisition. The implementation must not re-arm, run continuously, or issue a new acquisition between the image and CSV operations.

Recommended naming:

```text
capture_20260901_103001_0042.png
capture_20260901_103001_0042.csv
capture_20260901_103001_0042.json   # optional manifest
```

Acceptance:

- Image and CSV use the same event ID and sequence number.
- No acquisition/re-arm command occurs between the two reads.
- Failure of the second artifact is reported as a partial event; it must not be silently counted as a fully successful capture.

### A4 - Timed waveform logging

Behavior:

- Periodically export enabled channels to a single full-record CSV.
- Reuse current deterministic binary waveform acquisition and CSV export APIs.
- No screenshot transfer.
- Interval scheduler uses the same no-overlap rules as A1.

Acceptance:

- Exported point count matches configured/applied full record length.
- Repeated logging does not accumulate queued stale jobs.

### A5 - Measurement logger

Behavior:

- User selects any subset of MEAS1..MEAS8.
- Poll at a configurable interval.
- Append values to one run CSV rather than creating a new file per poll.
- Include at minimum:
  - UTC timestamp;
  - local timestamp;
  - elapsed run time;
  - sequence/sample number;
  - selected measurement values;
  - validity/error indication when a value cannot be read.
- Flush regularly so a crash does not lose the full run.

Recommended columns:

```text
utc_time,local_time,elapsed_s,sample,MEAS1,MEAS2,...,status
```

Acceptance:

- Column order remains stable for the run.
- Missing/invalid measurement values are explicitly represented rather than shifting columns.
- Logger shutdown flushes and closes the file cleanly.

### A6 - Conditional capture

Behavior:

Supported initial operators:

- `>`
- `>=`
- `<`
- `<=`
- inside `[low, high]`
- outside `[low, high]`
- absolute delta greater than threshold

Required controls:

- Measurement slot.
- Operator.
- Threshold/limits.
- Consecutive-match debounce count.
- Cooldown/minimum interval between captures.
- Artifact action: image, CSV, image+CSV, optional manifest.

Acceptance:

- Persistent out-of-limit state cannot fill the disk because cooldown is enforced.
- Debounce resets correctly when the condition becomes false.
- Invalid measurement reads do not count as condition matches.

### A7 - Burst capture

Behavior:

- Configurable finite count `N`.
- Configurable delay between events.
- Support at least:
  - image only;
  - CSV only;
  - image + CSV;
  - single -> wait complete -> capture -> re-arm sequence.
- Uses the same controller/executor as other modes; do not implement a second loop in the GUI.

Acceptance:

- Exactly N successful/attempted events according to selected count semantics.
- Stop cancels future burst events without corrupting the active artifact write.

### A8 - Run duration/count limits

Behavior:

- Optional maximum capture/event count.
- Optional maximum elapsed run duration.
- If both are configured, stop at the first reached limit.
- Limits apply to all recurring/burst modes.
- UI shows remaining count/time when determinable.
- Run report stores the stop reason.

Acceptance:

- Boundary condition cannot create one extra event after the limit.
- Stale timer callbacks after stop are ignored through the controller generation/run token.

### A9 - File retention

Required retention policies:

- Keep last N automation files/events.
- Keep automation storage below maximum GB.
- Delete automation files older than N days.

Safety requirements:

- Retention may delete **only files owned by the active automation output/run directory**.
- Never traverse outside the configured automation root through `..`, symlink surprises, or malformed profile data.
- Apply retention only after an artifact is safely closed/committed.
- Never delete the currently active event files.
- Prefer deleting oldest eligible complete events first.
- Log every deletion and reclaimed byte count.
- Provide dry-run/preview information in the UI before enabling destructive retention.
- If retention cannot reclaim enough space, stop safely when the configured minimum-free-space threshold is reached.

Recommended policy order:

1. Age limit.
2. Count limit.
3. Size limit.
4. Minimum-free-space guard.

Acceptance:

- Tests prove files outside the automation root cannot be removed.
- Active files are protected.
- Size/count calculations remain deterministic after partial/failed events.
- Long-run qualification includes retention enabled.

### A10 - Automation profiles

Behavior:

- Save/load a complete automation job configuration as JSON.
- Profiles are versioned and validated before application.
- Include:
  - mode;
  - schedule;
  - selected actions;
  - trigger/re-arm options;
  - measurement logger/condition settings;
  - run limits;
  - retention policy;
  - retry/reconnect policy;
  - reporting options;
  - output subfolder/naming options specific to automation.
- Do not store transient runtime counters/state as configuration.
- Loading a profile never auto-starts automation.

Acceptance:

- Round-trip save/load preserves all supported configuration values.
- Unknown future schema versions fail with an actionable message rather than being partially applied.

### A11 - Automatic reconnect

Behavior:

- Detect transport-class failures using the repository's existing exception classification.
- Invalidate/close the failed retained session.
- Retry after configurable backoff.
- Recreate the session through the existing worker-owned `PersistentScopeSession` or short-lived session path.
- Re-validate instrument identity/availability before continuing when appropriate.
- Do not reconnect blindly for validation or protocol-configuration errors.
- Track reconnect attempts/successes in automation statistics and report.

Recommended defaults:

- Event retries: 2.
- Retry delay: 1 s with optional bounded backoff.
- Stop after 5 consecutive failed events.

Acceptance:

- Simulated transport drop recovers without concurrent sessions.
- Old/stale session objects are not reused after transport failure.
- Reconnect cannot duplicate the previously completed trigger event.
- Hardware qualification includes cable/network interruption recovery.

### A12 - Automation report

Generate one run summary in JSON and optionally a flat CSV event log.

Minimum run-level fields:

- run/profile ID;
- application/package version;
- start/end UTC and local timestamps;
- elapsed duration;
- VISA resource and scope IDN;
- automation mode;
- configuration snapshot/profile reference;
- successful events;
- partial events;
- skipped events;
- failed events;
- retries;
- reconnect attempts/successes;
- retention deletions/bytes reclaimed;
- final stop reason;
- final error, if any.

Minimum event-level fields:

- sequence/event ID;
- scheduled time;
- actual start/end time;
- trigger/condition cause;
- artifact paths;
- status;
- elapsed operation time;
- retry count;
- error text/class when failed.

Acceptance:

- Report is finalized for normal Stop, count limit, duration limit, failure stop, and application-close shutdown.
- A crash-recovery strategy should preserve already-written event records even if the final summary cannot be completed.

## Delivery mapping

### Phase 0 - foundation

- Automation page and controller/executor models.
- Centralized page indices.
- Serialized scope-operation gateway.
- Status and statistics plumbing.

### Phase 1 - unattended periodic core

- A1 Periodic Image.
- A4 Timed waveform logging.
- A8 Run duration/count limits.
- A11 Automatic reconnect.
- Shared retry/no-overlap/collision-safe file handling.

### Phase 1B - 24/7 storage/reporting core

- A9 File retention.
- A12 Automation report.

A1/A4 should not be advertised for unrestricted 24/7 operation until A9/A11/A12 and long-duration qualification are complete.

### Phase 2 - acquisition/trigger evidence

- A2 Image on Trigger.
- A3 Image + CSV on Trigger.

Phase 2 is gated by a verified public DPO4000 acquisition-state API and real-hardware transition tests.

### Phase 3 - measurement and reusable workflows

- A5 Measurement logger.
- A6 Conditional capture.
- A7 Burst capture.
- A10 Automation profiles.

### Phase 4 - hardware qualification

Qualify the complete A1-A12 set where applicable with:

- USB/VISA and Ethernet transport where supported.
- Keep session OFF and ON.
- 1-hour functional soak.
- 8-hour overnight soak.
- 24-hour stability soak.
- Trigger/re-arm repetition.
- Forced timeout/disconnect/reconnect scenarios.
- Retention enabled with constrained test storage.
- Report integrity verification after normal and failure stops.

## Definition of done for 24/7 automation

The Automation tab should not be described as production-ready for unattended 24/7 operation until all of the following are true:

- A8 run limits are enforced without off-by-one events.
- A9 retention cannot delete outside the automation-owned root and passes constrained-storage tests.
- A11 reconnect passes induced transport failures without session overlap or trigger duplication.
- A12 reports accurately reconcile successful, partial, skipped, and failed events.
- Controller demonstrates no overlapping instrument operations.
- Memory/file-descriptor growth is bounded during a 24-hour soak.
- GUI remains responsive and can stop the run safely.
- Scope remains connectable and controllable after the run.
