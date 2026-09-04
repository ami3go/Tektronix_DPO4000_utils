# Logger Tab Implementation Plan

Status: **planned, not implemented**  
Target planning version: **v0.6.11**

## 1. Objective

Add a dedicated **Logger** page to DPO4000 Desk for sustained acquisition and long-duration recording of oscilloscope data.

Logger is intentionally separate from Automation:

- **Automation** performs discrete scheduled/triggered actions such as save Image + CSV.
- **Logger** repeatedly acquires and writes data for minutes, hours, or days while exposing throughput, buffering, skipped records, errors, reconnects, and disk use.

The design must remain a GUI orchestration layer over the reusable `dpo4000_utils` driver. Logger GUI/controller code must not introduce raw Tektronix SCPI strings or a second VISA implementation.

## 2. Important terminology: sustained logging vs true hardware streaming

The DPO4000 waveform API currently reads finite waveform records through `CURVE?`. Therefore the first Logger implementation must describe waveform operation as **continuous record logging** or **repeated acquisition logging**, not guaranteed zero-dead-time sample streaming.

For waveform sources, one logging cycle is conceptually:

```text
scope acquisition completes
        -> read selected waveform record(s)
        -> enqueue immutable record for writer
        -> re-arm/continue acquisition according to mode
        -> repeat
```

The UI must display the measured effective record rate and missed/skipped record count.

If later hardware qualification proves a model/transport supports a genuine streaming mechanism, it can be added as a separate driver capability. The GUI must not infer such support.

## 3. Current repository capabilities to reuse

### Already suitable foundations

- `WaveformData` structured waveform object.
- Binary waveform acquisition using compact integer arrays and scaling metadata.
- Supported waveform sources already include `CH1`, `CH2`, `CH3`, `CH4`, and `MATH`.
- Deterministic waveform transfer ranges and binary encodings.
- Public `read_measurement_value(slot)` and `get_measurement_setup(slot)` APIs for MEAS1..MEAS8.
- BUS1..BUS4 capability/configuration APIs.
- Existing serialized `_run_action(...)` / retained-session infrastructure.
- Existing File page output configuration.
- Existing transport-error classification and retained-session invalidation behavior.

### Driver capability still required

The existing BUS API configures and reads BUS decoder settings but does not expose decoded protocol transaction/event data.

Before BUS logging is enabled, add a public driver API such as:

```python
get_bus_decoded_events(bus: int, ...)
```

returning structured protocol-independent records, for example:

```python
BusDecodedEvent(
    bus=1,
    protocol="I2C",
    timestamp_s=...,
    event_type="DATA",
    fields={...},
    raw_text="...",
)
```

The exact DPO4000 SCPI mechanism and returned data must be verified against the programmer manual and real hardware before implementation.

## 4. Top-level application placement

Logger should be placed immediately after Automation and before File.

Canonical page order after Logger is introduced:

1. Connection
2. Channels
3. Measurement
4. Trigger
5. Acquisition
6. Automation
7. Logger
8. File
9. Display
10. Log

Update the centralized page definitions and keyboard shortcuts together. Avoid numeric page indices scattered through window subclasses.

## 5. Logger feature backlog

| ID | Feature | Behavior | Priority |
|---|---|---|---|
| L1 | Analog waveform logger | Repeatedly log CH1..CH4 records | Very high |
| L2 | MATH waveform logger | Include scope MATH waveform in record logging | High |
| L3 | CSV waveform output | Write selected waveform sources in human-readable CSV | High |
| L4 | Binary waveform output | Write efficient appendable binary records with full scaling metadata | Very high |
| L5 | Measurement logger | Continuously append MEAS1..MEAS8 values with timestamps | Very high |
| L6 | BUS decoder logger | Log decoded BUS1..BUS4 transactions/events | High; requires driver work |
| L7 | Mixed/synchronized record | Save waveform + MATH + measurement snapshot + BUS events for one acquisition epoch | Very high for validation |
| L8 | File rotation | Rotate by size, duration, record count, or date | Essential |
| L9 | Retention | Limit total GB / file count / age | Essential for 24/7 |
| L10 | Automatic reconnect | Recover session after timeout/disconnect | Essential for 24/7 |
| L11 | Bounded buffering | Separate acquisition and disk writing without unbounded RAM growth | Essential |
| L12 | Logger profiles | Save/load source, format, rate, rotation, retention and recovery config | High |
| L13 | Runtime health | Show actual rate, queue depth, bytes written, skipped/dropped records, errors | Essential |
| L14 | Run report | CSV/JSON summary with timestamps, counts, throughput, reconnects and errors | High |

## 6. Logging modes

Do not present L1..L14 as separate modes. The Logger should expose four operational modes.

### 6.1 Waveform records

Repeatedly store selected waveform sources.

Selectable sources:

- CH1
- CH2
- CH3
- CH4
- MATH

Controls:

- acquisition policy: `Continuous acquisitions` or `Single -> save -> rearm`;
- transfer point range / record length;
- desired record interval or `As fast as safely possible`;
- optional maximum run duration / record count;
- output: CSV or Binary.

`As fast as safely possible` means start the next acquisition/transfer only when the previous scope operation has completed and the bounded writer queue has capacity. It does not mean unbounded polling.

### 6.2 Measurements

Append MEAS1..MEAS8 values into one time-series stream.

Controls:

- select any MEAS slots;
- sample interval;
- timestamp source: PC UTC + local time;
- include measurement type/source metadata at file start;
- optional quality/status column for invalid/overflow scope readings.

Recommended CSV columns:

```text
utc_timestamp,local_timestamp,elapsed_s,MEAS1,MEAS2,...,MEAS8
```

If a measurement is unavailable, write an explicit empty/NaN/status field; do not silently shift columns.

### 6.3 BUS decoded events

Log structured decoded events from selected BUS1..BUS4 slots.

Controls:

- select BUS slots exposed by the connected scope;
- show protocol and label read from the driver;
- output normalized CSV and/or Binary;
- include acquisition-relative timestamp and host UTC timestamp;
- preserve protocol-specific fields in a structured field map for binary/JSON-compatible representation.

Suggested normalized CSV columns:

```text
utc_timestamp,acquisition_id,bus,protocol,event_time_s,event_type,address,data,flags,raw_text
```

Protocol-specific fields that do not map to common columns should be placed in a JSON-encoded `details` column rather than losing information.

### 6.4 Mixed record

Create one logical record from the same acquisition epoch containing any combination of:

- CH1..CH4 waveform records;
- MATH waveform;
- MEAS1..MEAS8 snapshot;
- decoded BUS events.

The writer must assign one `acquisition_id` / sequence number to the whole group.

For evidence-grade logging, do not re-arm or advance to the next acquisition until all requested scope-side data for the current acquisition has been read or the record has been explicitly marked partial/failed.

## 7. CSV output strategy

CSV is useful for interoperability but is inefficient for multi-million-point continuous waveform logging.

### Waveform CSV

Recommended default: **one rotated segment containing one or more acquisition blocks**, with block metadata rows or separate manifest.

For simple interoperability, support one-file-per-record as an optional mode, but do not make it the 24/7 default because it can create hundreds of thousands of small files.

Each waveform block must preserve:

- acquisition ID;
- UTC acquisition timestamp;
- source;
- label;
- point count;
- X unit / X increment / X zero / point offset;
- Y unit / multiplier / offset / zero;
- record start/stop indices;
- encoding and sample width.

A CSV export/converter must be able to reproduce engineering-unit X/Y values from binary logs.

### Measurement CSV

Append rows continuously to a rotated file and flush periodically.

### BUS CSV

Append one row per decoded event.

## 8. Binary output format

For sustained waveform logging, add a dependency-free, documented, append-only container, working name:

```text
DPO4LOG
```

Suggested extension:

```text
.dpo4log
```

### 8.1 Goals

- efficient for millions of integer waveform samples;
- appendable without rewriting previous data;
- self-describing;
- recoverable if the application/PC loses power during the final record;
- supports CH/MATH waveforms, measurements, BUS events, status and run metadata;
- schema versioned;
- convertible to CSV/JSON with a separate reader/converter API.

### 8.2 File structure

Conceptual framing:

```text
FILE HEADER
    magic = DPO4LOG
    schema version
    logger/run UUID
    scope IDN/resource
    start UTC timestamp

FRAME 1
    frame type
    frame length
    acquisition ID
    source metadata JSON length + JSON
    binary payload length + bytes
    checksum

FRAME 2
    ...
```

Frame types can include:

- `WAVEFORM`
- `MEASUREMENTS`
- `BUS_EVENTS`
- `STATUS`
- `ERROR`
- `END_OF_RUN`

Waveform payload should store the compact integer sample bytes plus the full `WaveformPreamble`, not expanded float64 voltage/time arrays.

The reader derives engineering units using the same scaling equation as `WaveformData`.

### 8.3 Crash recovery

A reader scans complete length-prefixed frames. If the final frame is incomplete or has an invalid checksum, it is ignored and reported as truncated. Previously completed frames remain readable.

Never keep a whole multi-hour log in RAM.

### 8.4 Converter

Plan a reusable API and CLI, for example:

```text
dpo4000-log inspect file.dpo4log
dpo4000-log convert file.dpo4log --csv output/
```

The reader/converter belongs outside the Qt UI so automated tests and future headless tools can use it.

## 9. Producer / writer architecture

Logger must not write large files on the GUI thread.

Recommended pipeline:

```text
Logger UI
    -> LoggerController
        -> ScopeRecordProducer
            -> existing serialized scope session/API
        -> bounded record queue
        -> LoggerWriter thread
            -> CSV writer or DPO4LOG writer
```

### 9.1 ScopeRecordProducer

Responsibilities:

- orchestrate acquisitions;
- read selected public driver data;
- assemble immutable `LoggerRecord` objects;
- never write output files;
- never execute concurrently with another scope operation.

### 9.2 Bounded queue

The queue must have a fixed maximum depth/byte budget.

Recommended default policy when full:

- do not allocate more memory;
- stop requesting another acquisition until capacity is available where acquisition control permits;
- if a newly completed acquisition cannot be preserved, increment an explicit skipped/dropped counter;
- optionally stop the run after a configurable number of queue-overflow events.

The UI must expose queue depth and peak queue depth.

### 9.3 LoggerWriter

Responsibilities:

- open/rotate/flush output files;
- serialize records;
- update written-byte/record counters;
- fsync only according to policy, not after every waveform block by default;
- emit structured writer failures back to the controller.

A disk error must never be converted into a scope reconnect attempt.

## 10. Data models

Suggested non-UI models:

```text
LoggerMode
LoggerState
LoggerSourceSelection
LoggerWaveformConfig
LoggerMeasurementConfig
LoggerBusConfig
LoggerOutputConfig
LoggerRotationPolicy
LoggerRetentionPolicy
LoggerRecoveryPolicy
LoggerProfile
LoggerRecord
LoggerStatistics
LoggerRunSummary
```

`LoggerRecord` should contain one acquisition ID and zero or more typed payloads:

```text
WaveformRecord[]
MeasurementSnapshot?
BusEvent[]
```

Use immutable snapshots once enqueued.

## 11. Runtime state machine

```text
Idle
 -> Starting
 -> Running
      -> Paused
      -> Recovering
      -> Stopping
 -> Failed
 -> Idle
```

Rules:

- Start validates source/format/output configuration before instrument activity.
- Pause stops scheduling new reads but lets the writer drain queued records.
- Stop stops new acquisition, drains or safely closes queued records according to policy, writes final run metadata, then returns Idle.
- Close application must request Logger stop before shutting down a retained scope session.
- stale producer/writer callbacks after Stop are ignored by generation token.

## 12. Connection and recovery policy

Logger should strongly recommend **Keep session** because repeated opening/closing of VISA for every logged record adds latency and failure surface.

On transport failure:

1. classify as transport error using existing error utilities;
2. invalidate/close retained session;
3. transition Logger to `Recovering`;
4. wait configured backoff;
5. reconnect through the same serialized session mechanism;
6. verify `*IDN?` / resource identity;
7. resume logging with a new record boundary;
8. increment reconnect count and emit a STATUS/ERROR frame/report entry.

Never silently duplicate the previous acquisition after reconnect.

## 13. File rotation

Support any combination of:

- maximum file size, e.g. 1 GB;
- maximum segment duration, e.g. 1 hour;
- maximum records per segment;
- daily UTC/local boundary.

Recommended binary default for 24/7 use:

```text
rotate at 1 GB OR 1 hour, whichever occurs first
```

File names:

```text
<run>_<start_timestamp>_<segment:04d>.dpo4log
```

CSV files use the same segment identity.

Rotation must occur only between complete frames/records.

## 14. Retention

Reuse the safety principles defined for Automation retention.

Controls:

- keep last N segments/files;
- maximum total Logger storage in GB;
- delete segments older than N days;
- stop if free disk below threshold.

Deletion rules:

- only files created within the Logger-owned run/output root;
- never delete the currently open segment;
- never follow symlinks outside the Logger root;
- delete oldest completed segments first;
- retention actions are recorded in the run report.

## 15. Performance and throughput telemetry

Always show:

- Logger state;
- elapsed run time;
- acquisition/record count;
- effective records/second;
- latest acquisition duration;
- latest transfer duration;
- latest write duration;
- current queue depth and peak depth;
- total bytes written;
- current segment size;
- skipped/dropped records;
- reconnect count;
- error count;
- free disk space.

For waveform logging also estimate:

```text
scope payload bytes/s
written bytes/s
average points/s
```

Do not label these values as oscilloscope sample rate. They are Logger transfer/storage throughput.

## 16. Interaction with Automation and manual controls

Only one subsystem may own repeated scope activity at a time.

Rules:

- Logger cannot start while Automation is running.
- Automation cannot start while Logger is running.
- Manual scope operations are disabled while a Logger scope transfer is active.
- Read-only local UI actions remain available.
- Stop Logger before changing Connection resource or transport settings.

Longer-term, both Automation and Logger should share a common `ScopeOperationCoordinator`/lease primitive rather than independently checking booleans.

## 17. Profiles

Logger profiles are JSON documents with schema versioning.

Persist:

- mode;
- selected sources;
- waveform transfer options;
- measurement slots/interval;
- BUS slots;
- CSV/Binary format;
- output folder/subfolder policy;
- rotation;
- retention;
- buffer size/overflow policy;
- reconnect/backoff policy;
- run limits.

Do not auto-start Logger on application launch in v1.

## 18. Run report

At end of run (and periodically checkpoint during long runs), write a machine-readable JSON summary and optional CSV event log.

Include:

- profile/config snapshot;
- app/package version;
- scope resource and IDN;
- start/end UTC and local time;
- elapsed time;
- output segments;
- selected sources;
- records produced/written/skipped/dropped;
- waveform point totals;
- BUS event totals;
- measurement row count;
- byte totals and average throughput;
- queue peak;
- reconnects/retries/errors;
- retention deletions;
- termination reason.

The report must reconcile with output-frame/row counts where practical.

## 19. Phase plan

### Phase L0 — architecture and UI shell

- Add Logger tab and centralized page order update.
- Add Logger models/state machine/controller skeleton.
- Add layout and validation without instrument logging.
- Add mutual exclusion with Automation design.

### Phase L1 — MEAS logger

Implement first because it is low bandwidth and exercises the long-run infrastructure safely:

- MEAS1..MEAS8 selection;
- periodic reads;
- append CSV;
- rotation;
- run limits;
- reconnect;
- report;
- bounded writer queue.

Acceptance:

- 10,000+ measurement rows in fake-driver test;
- no UI blocking;
- stable memory;
- correct fixed columns with unavailable values represented explicitly;
- clean rotation and stop.

### Phase L2 — CH/MATH waveform record logging

Implement:

- CH1..CH4 + MATH source selection;
- repeated record acquisition;
- CSV segments;
- binary DPO4LOG writer/reader;
- acquisition IDs;
- rate/queue/byte telemetry.

Acceptance:

- exact binary round-trip of raw integer samples and preamble;
- converted engineering values match `WaveformData`;
- no overlapping VISA operations;
- bounded memory with slow-writer simulation;
- incomplete final binary frame is recoverable.

### Phase L3 — mixed synchronized records

Implement waveform + MATH + MEAS snapshots under one acquisition ID.

Acceptance:

- all scope-side data are read before next re-arm for evidence-grade mode;
- partial failures are explicitly marked;
- report reconciles complete/partial records.

### Phase L4 — BUS decoded logging

Before implementation:

- verify DPO4000 programmer-manual decoded-event access;
- add public driver `BusDecodedEvent` API;
- hardware-qualify supported decoder types/models.

Then add BUS event CSV/Binary and mixed-record integration.

### Phase L5 — 24/7 qualification

Test:

- USB/VISA and Ethernet where available;
- Keep session ON/OFF, with ON as recommended production mode;
- measurement only;
- CH waveform only;
- CH + MATH;
- mixed records;
- BUS logging on supported hardware;
- CSV and Binary;
- forced disconnect/reconnect;
- slow/full disk scenarios;
- rotation/retention.

Soak gates:

- 1 hour functional;
- 8 hour overnight;
- 24 hour stability;
- optionally 72 hour qualification before declaring sustained Logger production-ready.

## 20. Test strategy

### Unit

- config validation;
- profile schema;
- state transitions;
- rotation decisions;
- retention containment;
- queue capacity/overflow;
- binary frame encode/decode;
- CRC/truncated-frame recovery;
- CSV column stability;
- measurement parsing;
- run-report reconciliation.

### Fake-driver integration

- producer/writer decoupling;
- slow disk simulation;
- transport disconnect and reconnect;
- stale callbacks after Stop;
- no duplicate acquisition IDs;
- mixed-record partial failure.

### Qt runtime

- lazy Logger page construction;
- dynamic source controls;
- Start/Pause/Stop state;
- live throughput widgets;
- application close with active Logger;
- mutual exclusion with Automation.

### Driver boundary

Add tests forbidding raw `.write(...)` / `.query(...)` Tektronix commands in Logger GUI/controller/writer modules.

### Hardware

Every hardware Logger test must have finite duration/record limits and write to an explicit temporary/bench output root.

## 21. Production readiness criteria

Do not call Logger production-ready for 24/7 use until:

- binary format has a versioned reader and corruption/truncation recovery tests;
- memory remains bounded under slower-than-acquisition writer conditions;
- disk-full/permission failures stop safely and preserve readable completed data;
- reconnect does not duplicate acquisition IDs;
- file rotation and retention are proven safe;
- run summary reconciles records/rows/frames;
- GUI remains responsive during high-volume transfers;
- 24-hour hardware soak passes with bounded memory/resource use;
- expected transfer dead time / effective record rate is documented for tested configurations.

## 22. Recommended first implementation slice

Implement **Measurement Logger (L1)** first, then **CH/MATH waveform logging with binary output (L2)**.

This order establishes the sustained-run controller, queue, writer, rotation, retention, reconnect and reporting infrastructure before large waveform payloads are introduced. BUS decoded logging should remain disabled until a verified public driver decoded-event API exists.
