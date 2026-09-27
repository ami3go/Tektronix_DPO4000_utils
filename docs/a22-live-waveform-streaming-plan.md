# A22 Live Waveform Streaming — Detailed Implementation Plan

## Status

**Planning only. No A22 implementation is authorized by this document.**

A22 must not start implementation until the current feature stack has completed its qualification/integration gate:

```text
A14 Advanced Trigger
→ A15 Test Recipe / Sequencer
→ A16 Pass/Fail Rule Engine
→ A18 Evidence Bundle
→ A20 Measurement Trend Dashboard
→ A21 Scientific Export
→ A25 Headless Job Runner
→ full accumulated regression + DPO4054 qualification
→ A22 Live Waveform Streaming
```

The immediate project priority remains testing, hardware qualification, retargeting, and merging the existing feature PR chain.

---

## 1. Purpose

A22 adds a responsive live waveform view by repeatedly acquiring bounded waveform snapshots through the existing public DPO4000 driver API and publishing the newest completed frame to DPO4000 Desk.

A22 is **not** intended to expose the oscilloscope ADC as a lossless continuous sample stream. The DPO4054 remains the acquisition authority; A22 repeatedly transfers completed waveform records over VISA and presents them with bounded latency and bounded memory.

The design must preserve the project's core invariant:

> Streaming may increase update frequency, but it must not bypass the public driver, create unbounded worker queues, freeze the Qt event loop, corrupt instrument state, or degrade cancellation/shutdown/reconnect behavior.

---

## 2. Goals

A22 shall provide:

- live waveform display for CH1..CH4 initially;
- selectable single-channel and multi-channel streaming;
- selectable transfer sizes: 1k, 10k, 100k, 1M, and Full/best-effort;
- configurable target refresh cadence;
- bounded latest-frame buffering;
- explicit frame-drop/backpressure accounting;
- acquisition/render latency statistics;
- pause/resume/stop;
- clean coexistence with the existing serialized scope worker;
- deterministic shutdown and cancellation semantics;
- integration with A20 plotting/decimation rather than a second plotting architecture;
- optional downstream capture hooks for A18/A21 after local streaming is stable;
- reusable framework-neutral data structures so later headless/WebSocket work does not depend on Qt.

---

## 3. Non-goals for the first A22 release

The first release shall **not** attempt:

- lossless continuous ADC streaming;
- guaranteeing every oscilloscope acquisition is transferred;
- 20 FPS at 1M points;
- arbitrary raw SCPI streaming commands from the GUI;
- multiple simultaneous VISA sessions to the same instrument;
- background streaming while an A15 recipe owns the scope;
- streaming while A18 is capturing evidence from the same session;
- streaming while A21 is exporting from the same session;
- browser/WebSocket remote streaming;
- video/screen-PNG streaming as the primary live view;
- automatic scope configuration changes merely to increase frame rate;
- silently changing acquisition mode, trigger mode, record length, channel state, or horizontal scale.

Remote streaming is explicitly a later extension after local A22 is qualified.

---

## 4. User-visible concept

The user selects sources, transfer size, and target update rate, then starts a live stream.

Example configuration:

```text
Sources:         CH1, CH2
Transfer points: 10k
Target rate:     10 Hz
Render budget:   2k points / channel
Buffer policy:   latest completed frame
```

Desk continuously shows:

```text
State: STREAMING
Acquired: 1248 frames
Rendered: 1210 frames
Dropped: 38 frames
Skipped polls: 12
Acquire rate: 9.8 fps
Render rate: 9.5 fps
Transfer: 3.7 MB/s
Acquisition p50/p95/p99
Frame age p50/p95/p99
Render p50/p95/p99
Last error / reconnect count
```

The statistics are part of the feature contract, not debug-only diagnostics.

---

## 5. Architecture

```text
DPO4054
   │
   │ public read_waveform/read_enabled_waveforms API
   ▼
Existing serialized scope worker
   │
   │ exactly one A22 poll in flight
   ▼
A22 stream controller
   │
   ├── sequence number
   ├── monotonic timestamps
   ├── bounded latest-frame slot
   ├── counters/statistics
   └── explicit drop/skip policy
   │
   ▼
A20-compatible plot/update model
   │
   ├── decimation outside paint path
   └── fixed render budget
   │
   ▼
Qt presentation
```

### Required boundaries

A22 GUI code must not:

- access `scope.scope`;
- call raw `.query()` / `.write()` on VISA;
- create a second `ResourceManager`;
- parse IEEE waveform blocks;
- own scaling formulas already implemented by `WaveformData`;
- perform large sample conversion/compression on the Qt event loop.

Instrument behavior remains in `dpo4000_utils.waveform` / public driver methods.

---

## 6. Core data model

A framework-neutral module should be introduced, tentatively:

```text
dpo4000_utils/live_stream.py
```

Proposed types:

```python
@dataclass(frozen=True)
class WaveformStreamConfig:
    sources: tuple[str, ...]
    point_count: int | None
    target_hz: float
    render_points: int
    encoding: str = "RIBINARY"
    sample_width: int = 2

@dataclass(frozen=True)
class WaveformStreamFrame:
    sequence: int
    requested_at_s: float
    acquired_at_s: float
    published_at_s: float
    waveforms: Mapping[str, WaveformData]

@dataclass(frozen=True)
class WaveformStreamStats:
    state: StreamState
    frames_requested: int
    frames_acquired: int
    frames_rendered: int
    polls_skipped: int
    frames_replaced: int
    acquisition_errors: int
    reconnects: int
    acquisition_rate_hz: float
    render_rate_hz: float
    transfer_bytes_per_s: float
    acquisition_latency: DistributionStats
    frame_age: DistributionStats
    render_latency: DistributionStats
```

State enum:

```text
IDLE
STARTING
STREAMING
PAUSED
STOPPING
STOPPED
ERROR
```

The exact names may change during implementation, but the responsibilities should remain stable.

---

## 7. Scheduling model

### 7.1 Do not run an infinite loop inside the scope worker

An infinite worker-side streaming loop would make worker ownership, cancellation, recipes, reconnect, and shutdown unnecessarily difficult.

Instead, Desk should schedule **one bounded waveform acquisition action at a time** through the existing worker.

Conceptually:

```text
QTimer deadline
    ↓
if no poll in flight:
    submit one public-driver waveform acquisition
else:
    increment polls_skipped
```

When the worker returns:

```text
validate frame
→ publish newest frame
→ clear in-flight flag
→ next timer deadline may submit again
```

This provides natural backpressure and keeps queue depth bounded at zero/one A22 acquisition.

### 7.2 Absolute monotonic scheduling

Cadence must be based on absolute monotonic deadlines, not:

```python
work()
sleep(interval)
```

Use:

```text
next_deadline = start + sequence * period
```

If a transfer takes longer than the period, do not enqueue catch-up frames. Skip missed deadlines and account for them explicitly.

### 7.3 In-flight invariant

At all times:

```text
A22 worker requests queued/in-flight <= 1
```

This is a hard regression invariant.

---

## 8. Buffering and drop policy

A22 should use a **latest-frame** model, not a FIFO of waveform records.

Initial policy:

```text
worker result arrives
    ↓
if previous completed frame has not yet been rendered:
    replace it
    frames_replaced += 1
publish newest frame only
```

This keeps live latency low and memory bounded.

Do not preserve stale frames simply to make the displayed frame counter continuous.

For recording use cases, A22 must not silently reuse the UI latest-frame slot as a lossless recorder queue. Recording needs a separately qualified bounded writer pipeline.

---

## 9. Memory policy

The live-view memory budget must be deterministic.

At minimum hold only:

- one in-flight acquisition result;
- one latest completed frame awaiting render;
- one currently rendered/owned frame if Qt requires it;
- bounded statistics windows.

No unbounded history of full waveform frames.

A20's trend history remains separate because it stores scalar/decimated history rather than full transferred waveform records.

Memory tests must verify steady-state RSS/traced-memory behavior for 1k, 10k, 100k, and 1M configurations.

---

## 10. Rendering strategy

A22 should reuse A20's plotting/decimation concepts.

Rendering full 100k/1M sample arrays directly on every frame is not acceptable.

Pipeline:

```text
WaveformData
   ↓
scaling / view preparation off UI-critical path where practical
   ↓
spike-preserving min/max decimation
   ↓
fixed-size render arrays
   ↓
Qt paint/update
```

Proposed render budgets:

```text
500
1k
2k
5k points per source
```

The user may choose a render budget independently of transfer size.

This is important: acquiring 100k samples and rendering 2k is often more useful than transferring only 2k samples, because the scope record still contains narrow events that decimation can preserve.

---

## 11. Initial target-rate options

Expose conservative target choices rather than implying guaranteed rates:

```text
1 Hz
2 Hz
5 Hz
10 Hz
20 Hz
Maximum / best effort
```

These are **requested cadences**, not guaranteed scope frame rates.

The UI must display actual measured acquisition/render rates.

A22 qualification will establish realistic limits separately for:

- USB VISA;
- TCPIP/VXI-11 VISA;
- source count;
- transfer size;
- acquisition mode/record configuration already active on the scope.

No hard performance claim should be made before DPO4054 measurements exist.

---

## 12. Source selection

Phase 1:

```text
CH1
CH2
CH3
CH4
```

Multi-channel frame alignment should use the existing validated waveform alignment rules where applicable.

Later, after CH1..CH4 qualification:

```text
MATH
REF1..REF4
```

BUS visualization is not part of A22 waveform streaming v1.

---

## 13. Instrument-state policy

Default A22 behavior is **observational**.

Starting a stream must not automatically change:

- RUN/STOP state;
- trigger mode/type;
- horizontal scale;
- record length;
- acquisition mode;
- channel display state;
- channel vertical settings.

A22 only controls the outgoing waveform transfer window/encoding required by the public waveform API.

If a future mode requires continuous acquisition or explicit trigger behavior, it must be a separately visible opt-in mode with save/restore qualification.

---

## 14. Interaction with existing features

### A14 Advanced Trigger

Streaming must not alter trigger configuration. Trigger changes made by the user should naturally appear in subsequent frames.

### A15 Recipe / Sequencer

A15 execution and A22 streaming shall be mutually exclusive in v1.

Starting a recipe while streaming should require the stream to stop first; starting streaming while a recipe runs should be disabled/rejected.

Do not queue a recipe behind an indefinite live stream.

### A16 Rule Engine

A16 may later evaluate scalar values derived from stream frames, but that is not required for v1.

### A18 Evidence Bundle

A18 capture should use a stable completed frame or temporarily stop streaming before acquiring its own evidence. The first implementation should prefer **stop/serialize/capture/resume only if explicitly designed and tested** rather than hidden concurrent capture.

### A20 Measurement Trend Dashboard

A20 is the preferred visualization infrastructure to reuse where practical. A22 should add waveform-frame presentation without duplicating A20's bounded-memory/statistics principles.

### A21 Scientific Export

A21 export remains an explicit snapshot operation. v1 should not continuously write every stream frame to NPZ/DPOZ.

A later "record stream" mode can batch selected frames into a separately specified format after throughput/storage qualification.

### A25 Headless Job Runner

A25 does not need live streaming for A22 v1. However, the A22 core model must remain Qt-independent so a later command such as a fixed-duration capture job can be added without redesign.

---

## 15. Desk UI proposal

Preferred placement: existing waveform/File or Measurement-oriented surface depending on the final integrated Desk layout after current PRs merge. Do not add a top-level page until the integrated UI is reviewed.

Controls:

```text
Sources             [CH1] [CH2] [CH3] [CH4]
Transfer points     [1k | 10k | 100k | 1M | Full]
Target rate         [1 | 2 | 5 | 10 | 20 | Max] Hz
Render budget       [500 | 1k | 2k | 5k]
                    [Start] [Pause] [Resume] [Stop]
```

Status area:

```text
Actual FPS
Transfer MB/s
Acquisition latency
Frame age
Render latency
Skipped deadlines
Replaced frames
Last error
Session/reconnect state
```

Plot:

- shared X-axis for aligned channels;
- independent channel visibility;
- no per-frame automatic zoom unless explicitly selected;
- retain user zoom/pan across frame updates;
- clear indication if frames are stale or streaming has stopped.

---

## 16. Error and reconnect behavior

A transient transport failure must not create worker/thread/session growth.

Required policy:

1. mark frame acquisition failed;
2. increment error counter;
3. stop issuing normal cadence requests while recovery is active;
4. use the existing session/reconnect architecture rather than creating an A22-specific VISA session;
5. after successful recovery, resume from a fresh monotonic deadline rather than attempting missed frames;
6. surface the failure/recovery status in Desk.

Repeated failure must transition the stream to `ERROR` after a bounded policy rather than retry forever invisibly.

Exact retry policy should be selected after the integrated session/reconnect code is reviewed post-merge.

---

## 17. Cancellation and shutdown

`Stop` must:

- prevent submission of another poll immediately;
- let an already active public-driver transfer finish or fail under its bounded VISA timeout;
- discard a late frame if stop generation/state no longer matches;
- leave no queued follow-up work;
- return to a stable stopped state.

Use a **generation token** or equivalent sequence guard so a result from a previous stream instance cannot be rendered after restart.

Shutdown must not wait on an endless stream loop because no endless worker loop exists.

---

## 18. Generation token design

Every Start increments a stream generation:

```text
generation = generation + 1
```

Each submitted worker action captures that generation.

On completion:

```text
if result.generation != current_generation:
    discard result
```

Stop also invalidates the active generation.

This prevents race conditions such as:

```text
Start A
→ slow acquisition A in flight
→ Stop
→ Start B
→ acquisition A returns late
```

A late A frame must never overwrite B.

---

## 19. Statistics implementation

Store bounded rolling latency samples, for example the latest 512 or 1024 observations.

Calculate:

```text
min
p50
p95
p99
max
sample_count
```

for:

- worker submit → acquisition start if observable;
- acquisition duration;
- acquisition completion → frame publication;
- frame publication → render completion;
- total frame age at render.

Also maintain cumulative counters separately from rolling distributions.

The statistics implementation should be reusable by performance tests and not rely on text scraped from the GUI.

---

## 20. Performance qualification matrix

At minimum test:

### Transfer sizes

```text
1k
10k
100k
1M
largest practical/qualified DPO4054 record
```

### Source counts

```text
1 channel
2 channels
4 channels
```

### Requested rates

```text
1 Hz
5 Hz
10 Hz
20 Hz / best effort where applicable
```

### Transports

```text
USB/VISA
TCPIP/VXI-11 VISA
```

Record:

```text
actual acquisition FPS
actual render FPS
samples/s
MB/s
acquisition p50/p95/p99/max
frame-age p50/p95/p99/max
render p50/p95/p99/max
GUI heartbeat p50/p95/p99/max
skipped deadlines
replaced frames
errors
RSS / Python peak memory
thread count
FD count
```

Do not compare USB and TCPIP numbers as if they were the same baseline.

---

## 21. GUI responsiveness gate

Run the existing/extended Qt heartbeat watchdog while streaming.

Required cases:

- 10k single-channel;
- 100k single-channel;
- 100k four-channel;
- 1M single-channel;
- highest practical DPO4054 case.

A22 must fail qualification if waveform streaming works numerically but causes unacceptable multi-second UI stalls.

The important metric is not merely FPS; it is **interactive latency while streaming**.

---

## 22. Fake-driver tests

Create deterministic fake waveform sources supporting:

```text
0 ms latency
10 ms
100 ms
500 ms
blocked until release
timeout
transport failure
malformed waveform
changing sample count
changing X metadata
```

Verify:

- never more than one poll in flight;
- missed cadence becomes `polls_skipped`, not queue growth;
- latest-frame replacement is bounded;
- stop during slow acquisition works as specified;
- late generation results are discarded;
- pause submits no new reads;
- resume restarts cadence without catch-up burst;
- malformed frames do not replace the last valid frame;
- retry/reconnect does not create extra sessions/threads;
- shutdown remains bounded.

---

## 23. Functional test matrix

### Configuration validation

Cover:

- empty source list;
- duplicate sources;
- unsupported sources;
- zero/negative/non-finite target rate;
- excessively high target rate;
- invalid transfer size;
- invalid render budget;
- invalid encoding/sample width;
- wrong types;
- injection-like strings where strings are accepted.

Rejected configuration must perform zero instrument I/O.

### State machine

Cover all legal transitions and reject illegal ones:

```text
IDLE → STARTING → STREAMING
STREAMING → PAUSED → STREAMING
STREAMING → STOPPING → STOPPED
PAUSED → STOPPING → STOPPED
any active state → ERROR when recovery policy is exhausted
STOPPED → STARTING
```

### Backpressure

Prove queue/in-flight depth never exceeds one acquisition.

### Memory

Prove full waveform history does not grow with runtime.

---

## 24. Hardware qualification

Initial DPO4054 HIL should be read-only with respect to acquisition/trigger configuration.

Qualification sequence:

1. connect and verify expected DPO4054 IDN;
2. capture baseline setup/read-only state required for diagnosis;
3. stream CH1 at 1k for a short bounded duration;
4. repeat at 10k, 100k, 1M;
5. repeat selected cases for 2 and 4 channels;
6. verify waveform metadata/sample counts each frame;
7. verify no unexpected trigger/acquisition configuration change;
8. capture throughput/latency/GUI-heartbeat statistics;
9. stop stream and verify no outstanding worker activity;
10. disconnect/reconnect and rerun a short case;
11. preserve artifacts as JSON/JUnit/performance evidence.

If Full-record streaming requires a scope state that differs materially by acquisition mode, document and qualify those modes separately rather than hiding the dependency.

---

## 25. Soak qualification

After short HIL is clean:

### 1-hour engineering soak

Use representative 10k/100k live streaming and monitor:

- RSS slope;
- Python traced-memory slope;
- thread count;
- FD count;
- actual FPS trend;
- latency trend;
- skipped/replaced frame rate;
- reconnects/errors.

### Release soak

A22 changes worker/session behavior enough that it should participate in the project's normal release soak policy after merge.

A successful soak with steadily worsening frame latency is a failure.

---

## 26. Proposed implementation phases

### Phase A — Core model only

- config/state/frame/stats dataclasses;
- generation token;
- bounded latest-frame slot;
- deterministic fake-clock scheduling helpers;
- no Qt and no hardware changes.

Gate: pure tests green.

### Phase B — Serialized worker acquisition

- one-public-driver-read-per-poll;
- in-flight guard;
- source/point-count handling;
- slow/fault fake-driver tests;
- no plot yet.

Gate: queue/backpressure/cancel/reconnect tests green.

### Phase C — Desk live plot

- UI controls;
- A20-compatible decimation/render path;
- zoom/pan preservation;
- frame/stats projection;
- GUI heartbeat tests.

Gate: full PySide6 regression + responsiveness green.

### Phase D — DPO4054 qualification

- USB/TCPIP cases;
- 1k→1M scaling;
- 1/2/4 channel cases;
- controlled timing evidence.

Gate: real hardware and performance acceptance.

### Phase E — Optional snapshot integrations

Only after D is stable:

- capture latest stable frame into A18 evidence;
- export selected stable frame through A21;
- explicit semantics for stop/capture/resume if required.

These integrations must not turn A18/A21 into continuous recorders.

### Phase F — Remote streaming design

Separate follow-on feature, not part of initial A22:

```text
A22 local stream → bounded encoder → WebSocket → browser/Python client
```

Design only after local throughput, latency, and memory behavior are known.

---

## 27. Acceptance criteria

A22 software is ready for HIL when:

1. all preexisting regression tests pass;
2. invalid configs generate zero unintended I/O;
3. one-in-flight invariant is proven;
4. no unbounded frame queue/history exists;
5. generation races are covered;
6. pause/resume/stop behavior is deterministic;
7. slow/failing I/O does not grow worker/thread/session count;
8. full PySide6 suite passes;
9. GUI heartbeat remains within the agreed smoke budget;
10. 1k/10k/100k/1M synthetic scaling shows no pathological algorithmic growth;
11. documentation and test matrix are complete.

A22 is complete only after:

12. DPO4054 HIL passes;
13. USB/TCPIP timing baselines are captured separately;
14. practical source-count/record-size operating envelopes are documented;
15. no unexpected scope configuration change is observed;
16. stop/reconnect/shutdown timing remains within regression budget;
17. soak shows no progressive resource or latency degradation.

---

## 28. Risks and mitigations

| Risk | Mitigation |
|---|---|
| VISA transfer slower than requested cadence | one-in-flight guard + skipped-deadline accounting |
| stale GUI frames | latest-frame replacement, no FIFO |
| 1M rendering freezes UI | fixed render budget + decimation |
| memory growth | max 1–2 completed full frames + bounded stats |
| stop/restart race | generation token |
| worker starvation | streaming submits only one bounded action at a time |
| recipe/evidence/export conflict | mutually exclusive v1 ownership policy |
| transport disconnect | existing reconnect/session machinery, bounded recovery |
| hidden scope-state changes | observational default + HIL before/after checks |
| misleading 'real-time' claim | report actual FPS/latency/drops; describe as repeated waveform snapshots |
| network/browser scope creep | keep WebSocket work out of A22 v1 |

---

## 29. Work explicitly deferred until current qualification is complete

Before any A22 implementation branch is created, finish the current stack:

```text
1. Bring the self-hosted `dpo4000` runner online.
2. Execute pending A14/A15/A16/A18/A20/A21/A25 hardware gates.
3. Fix any real DPO4054 failures found by those gates.
4. Remove temporary qualification workflows after successful evidence capture.
5. Merge/retarget the stacked PR chain in dependency order.
6. Run accumulated main-branch regression.
7. Capture controlled R0-T measurements.
8. Perform required hardware/release soak.
9. Freeze the resulting integrated baseline.
10. Only then branch A22 from that known-good integrated baseline.
```

This prevents A22 performance/concurrency work from masking defects in the current feature stack.

---

## 30. Recommended first A22 implementation target

When implementation is eventually authorized, start with the smallest meaningful configuration:

```text
CH1 only
10k transfer points
5 Hz requested rate
2k render budget
TCPIP/VXI-11 and USB both measurable
latest-frame policy
no recording
no auto-reconnect-specific behavior beyond existing session policy
```

Once that path is fully deterministic, add 1k/100k/1M, higher cadence, and multi-channel operation incrementally.

This keeps the first implementation focused on architecture and backpressure rather than chasing maximum frame rate prematurely.
