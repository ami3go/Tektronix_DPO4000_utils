# DPO4000 Utils Regression Test Plan

## Purpose

This document defines the regression gate for all work after v0.8.0, including A14, A15, A16, A18, A20, A21, and A25.

A feature is not complete merely because the expected values are correct. It must also preserve established timing, responsiveness, throughput, scheduling behavior, resource use, and hardware recovery characteristics.

The baseline is split into two independent snapshots:

- **R0-F — Functional baseline**: behavior, validation, SCPI, state, GUI contract, error behavior, and HIL correctness.
- **R0-T — Timing/performance baseline**: latency, jitter, drift, throughput, queue behavior, GUI responsiveness, cancellation/reconnect/shutdown latency, and long-run resource/performance stability.

Both baselines must be captured from a known-good commit before A14 begins. Snapshot updates must be explicit and reviewed; they must never be regenerated automatically simply to make a failing test pass.

---

## 1. Feature implementation order

Development order is fixed:

```text
R0-F + R0-T
    ↓
A14 Advanced Trigger
    ↓
A15 Test Recipe / Sequencer
    ↓
A16 Pass/Fail Rule Engine
    ↓
A18 Evidence Bundle
    ↓
A20 Measurement Trend Dashboard
    ↓
A21 Scientific Export
    ↓
A25 Headless Job Runner
```

Each feature must pass the full accumulated regression suite before the next feature starts.

---

## 2. Regression levels

| Level | Scope | Primary purpose |
|---|---|---|
| L0 | Pure validation | Boundary, type, enum, non-finite and injection handling |
| L1 | Command contract | Input → normalized value → exact SCPI/query sequence |
| L2 | Fake instrument | Error, timeout, malformed reply, disconnect and retry behavior |
| L3 | Functional snapshot | Current public state and normalized behavior |
| L4 | GUI integration | Qt control/controller/driver contract |
| L5 | Deterministic timing semantics | Timeouts, retry schedules, cancellation and cadence with fake clock |
| L6 | Performance baseline | Latency distributions and throughput regression |
| L7 | Concurrency/backpressure | Queue growth, starvation, drops, writer throughput and drain behavior |
| L8 | GUI responsiveness | Event-loop stalls and UI callback latency under load |
| L9 | Hardware functional HIL | Real DPO4054 read-only and reversible correctness |
| L10 | Hardware performance HIL | Real USB/TCPIP latency and throughput regression |
| L11 | Long-duration soak | Memory/resource leaks, drift and progressive performance degradation |

---

## 3. R0-F — Functional baseline

### 3.1 Standard boundary matrix

Every externally supplied indexed/numeric parameter with a software-defined range must cover:

```text
far below minimum
below minimum
just below minimum
minimum
nominal value(s)
maximum
just above maximum
above maximum
far above maximum
wrong type
empty value
None
NaN
+Inf
-Inf
SCPI separator injection
embedded newline/carriage-return injection
```

Example for channel 1..4:

| Input | Expected |
|---:|---|
| -100 | reject |
| -1 | reject |
| 0 | reject |
| 1 | accept |
| 2 | accept |
| 3 | accept |
| 4 | accept |
| 5 | reject |
| 6 | reject |
| 999 | reject |

For every rejected input:

```text
expected exception
AND zero VISA writes
AND zero unintended VISA queries
```

### 3.2 Enum matrix

Every legal enum member must have a positive test. Invalid, empty, malformed, wrong-type and command-injection values must be rejected before I/O.

### 3.3 Hardware-dependent physical limits

Do not invent fixed software limits for values whose valid range depends on DPO model, probe, channel configuration, acquisition mode or firmware.

Separate:

- structural validation: type, finite number, legal syntax, safe SCPI representation;
- instrument capability validation: verified programmer-manual limits and/or real instrument readback/capability checks.

### 3.4 Functional snapshots

Capture normalized behavior for:

- CH1..CH4;
- MATH;
- REF1..REF4;
- BUS1..BUS4 capability/configuration;
- MEAS1..MEAS8;
- trigger;
- horizontal;
- acquisition;
- display;
- setup save/restore;
- connection/session behavior;
- Automation A1..A12;
- Logger modes and output contracts.

Snapshots must represent public behavior, not implementation details or Python object `repr()` output.

### 3.5 GUI contract snapshot

Capture by Qt object/property inspection rather than pixel screenshots:

- page names/order;
- major actions and controls;
- selector ranges;
- enabled/disabled relationships;
- controller-to-driver boundaries;
- lazy-page construction behavior;
- no nested GUI event loop in production worker paths.

---

## 4. R0-T — Timing and performance baseline

### 4.1 General rule

A test that only asserts "finished before a generous timeout" is a reliability/deadlock test, not a performance regression test.

For important operations, capture distributions using repeated runs and store at least:

```text
min
median (p50)
p95
p99
max
sample_count
```

Capture throughput where meaningful.

### 4.2 Timing metrics to baseline

At minimum measure:

| Operation | Timing metric |
|---|---|
| Application startup | process start → usable main window |
| Connection | connect request → usable IDN/session |
| Worker dispatch | submit → worker start |
| Worker callback | worker completion → GUI callback |
| Core refresh | refresh request → core state available |
| Full refresh | Core → REF → BUS completion |
| Channel apply | request → successful readback |
| MEAS1..8 refresh | total measurement update latency |
| Single acquisition | arm → acquisition complete |
| Triggered capture | trigger detection → artifact complete |
| PNG capture | request → valid PNG durable on disk |
| Waveform acquisition | request → parsed sample array |
| CSV export | samples ready → durable file |
| Logger enqueue | producer → queue |
| Logger write | enqueue → durable output |
| Logger stop | stop request → drained and closed |
| Reconnect | failure detection → usable replacement session |
| Cancel | cancel request → cancelled completion |
| Shutdown | shutdown request → worker/session terminated |
| A15 | per-step dispatch overhead and recipe completion |
| A16 | rule evaluation throughput/latency |
| A18 | evidence bundle completion |
| A20 | sample received → trend model/plot update |
| A21 | export throughput and round-trip time |
| A25 | CLI start → first operation and total recipe time |

### 4.3 Waveform scaling cases

Performance tests must exercise multiple waveform sizes so algorithmic regressions are visible:

```text
1k points
10k points
100k points
1M points
largest practical/qualified DPO4054 record length
```

Track both total latency and samples/second.

A change that remains fast for 1k points but becomes O(n²) at 1M points must fail regression.

### 4.4 Relative + absolute performance gate

Do not use fragile single-machine exact-time assertions.

Use both a relative threshold and a meaningful absolute delta. Example policy:

```text
FAIL if
    candidate_p95 > baseline_p95 × relative_limit
AND
    candidate_p95 - baseline_p95 > absolute_tolerance
```

Initial default for non-critical operations:

```text
relative_limit = 1.30
```

The absolute tolerance is operation-specific and must be established from the R0-T baseline.

Critical operations may also have a hard engineering ceiling independent of the baseline:

- GUI event-loop stall;
- cancellation latency;
- shutdown latency;
- reconnect downtime;
- logger drain time;
- missed cadence/deadline rate.

Threshold changes require explicit review.

---

## 5. Deterministic time tests with a fake clock

Wall-clock tests should not be used where deterministic virtual time is possible.

Scheduling, retry and timeout algorithms must accept/inject monotonic time/sleep abstractions where practical.

Use fake-clock tests for:

- timeout exact boundary;
- timeout just below/above boundary;
- retry delay sequence;
- reconnect backoff;
- run-duration limits;
- recipe Delay steps;
- cancellation during wait;
- periodic Automation cadence;
- Logger cadence;
- missed-deadline policy.

This keeps CI fast and eliminates timing flakiness.

---

## 6. Scheduler drift and jitter regression

Periodic work must be scheduled against an absolute monotonic deadline, not `work + sleep(interval)`.

For each periodic run record:

```text
sequence
scheduled_time
actual_start_time
actual_finish_time
jitter
operation_duration
missed_deadline
```

Test both simulated and real execution.

Required checks:

- no unbounded cumulative drift;
- p95/p99 jitter within baseline budget;
- expected event count matches elapsed time within policy;
- missed deadlines are counted explicitly;
- long-running work follows the defined skip/catch-up policy;
- system-clock changes do not corrupt monotonic scheduling.

Fake-clock regression should simulate thousands of periods without waiting in real time.

---

## 7. GUI responsiveness regression

Functional asynchronous architecture is not enough; expensive callbacks can still freeze the GUI.

Add an event-loop heartbeat watchdog while running heavy operations.

Recommended test mechanism:

- schedule a lightweight Qt heartbeat at a short interval;
- record expected and actual callback times;
- compute event-loop stall/jitter statistics;
- run the heartbeat while the tested operation is active.

Exercise at least:

- full scope refresh;
- 1M-point waveform processing;
- PNG capture;
- Logger load and drain;
- A18 evidence bundle generation;
- A20 trend rendering/update;
- A21 scientific export;
- A15 recipe execution.

Store:

```text
heartbeat p50 latency
heartbeat p95 latency
heartbeat p99 latency
maximum stall
missed heartbeats
```

A multi-second GUI stall is always a severe regression even when the final operation succeeds.

---

## 8. Concurrency and backpressure regression

The Logger and worker/session paths must be tested for sustained-load behavior, not only final correctness.

Measure:

```text
producer rate
consumer/writer rate
queue depth
peak queue depth
oldest-record age
dropped records
overflow events
write failures
drain time
```

Run representative load points around the intended operating range, for example:

```text
25%
50%
80%
100%
120%
```

of the qualified sustainable rate.

At sustainable load the queue depth must not have a persistent positive slope.

A short test where the queue has not overflowed yet is not sufficient if queue age/depth is continuously increasing.

---

## 9. Slow-I/O and fault-injection timing tests

Fake VISA/output implementations must support deterministic delay injection, for example:

```text
0 ms
10 ms
100 ms
500 ms
normal timeout
blocked until explicitly released
transport failure
```

While slow/failing I/O is active verify:

- GUI heartbeat remains alive;
- unrelated UI work does not synchronously wait;
- cancellation behavior remains bounded;
- queue remains bounded;
- Stop/Shutdown remains responsive according to policy;
- retry/backoff sequence is correct;
- one blocked operation cannot create unbounded session/thread growth.

---

## 10. Performance-specific regression additions to existing stress tests

Existing stress/reliability tests remain, but add explicit performance assertions/metrics rather than relying only on generous waits.

### Persistent scope session

For repeated fake-scope requests record:

- requests/second;
- submit → start queue latency;
- operation → callback latency;
- p50/p95/p99/max;
- cancellation latency;
- reconnect recovery latency;
- shutdown latency;
- number of live scope instances;
- worker/thread count.

### Logger writer

For FIFO drain tests record:

- records/second;
- enqueue p95/p99;
- queue wait age;
- drain time;
- output close time;
- queue-depth slope.

The current broad timeout remains as a deadlock guard, but a large slowdown relative to the R0-T baseline must fail separately.

---

## 11. HIL timing baseline

Real DPO4054 timing must be measured separately from fake-VISA timing.

Keep separate performance baselines for at least:

- USB/VISA;
- TCPIP/VISA.

Do not compare USB numbers directly with network numbers.

For each HIL case store:

```text
case_id
transport
scope IDN
firmware
application version
commit SHA
duration_s
operation-specific latency/throughput
result
```

The existing per-case duration must become an input to regression acceptance, not only a diagnostic value.

Hardware timing tests must remain reversible where configuration is changed:

```text
save baseline
→ perform operation
→ verify
→ restore
→ verify restoration
```

---

## 12. Soak qualification: resource + performance stability

The 24 h / 72 h soak must evaluate both resource growth and timing degradation.

Continue recording:

- RSS;
- Python traced memory;
- file descriptors;
- thread count;
- failures;
- reconnects;
- cycle duration.

Add pass/fail analysis for:

```text
cycle p50/p95/p99/max
cycle-duration trend/slope
expected vs actual cycle count
missed cadence count
reconnect downtime
per-operation latency trend
throughput trend
```

A run that completes successfully but becomes progressively slower must fail qualification.

Compare early-run and late-run windows, for example first 10% vs last 10%, to detect progressive degradation.

---

## 13. CI execution tiers

### PR / every commit

Run:

- R0-F functional regression;
- deterministic fake-clock timing tests;
- fake-VISA fault and latency tests;
- GUI heartbeat responsiveness tests;
- short concurrency/backpressure tests;
- short performance smoke tests.

PR timing gates must use sufficiently robust budgets to avoid noise from shared CI hosts.

### Controlled/nightly performance runner

Run authoritative baseline comparisons on the same controlled machine/environment:

- p50/p95/p99 latency comparisons;
- waveform scaling;
- logger throughput;
- GUI responsiveness under load;
- reconnect/cancel/shutdown timing;
- export throughput.

### DPO4054 hardware/release qualification

Run:

- hardware functional HIL;
- USB timing suite;
- TCPIP timing suite where available;
- Automation/Logger HIL;
- release performance comparison to R0-T;
- 24 h soak for normal release qualification;
- 72 h soak for major architecture/session/logger changes.

---

## 14. Per-feature timing requirements

### A14 — Advanced Trigger

Add timing regression for:

- trigger configuration latency;
- trigger readback latency;
- Single arm → completion;
- timeout exactness;
- unsupported-trigger capability probe latency;
- no expansion of VISA timeout beyond intended bounds.

### A15 — Recipe / Sequencer

Add:

- per-step dispatch overhead;
- deterministic Delay timing;
- cancellation latency during Delay and I/O;
- pause/resume semantics;
- recipe scheduling drift;
- large recipe scalability;
- retry/backoff timing.

### A16 — Pass/Fail Rule Engine

Add:

- rules/second;
- p95/p99 evaluation latency;
- scaling with large AND/OR trees;
- no GUI-thread stalls during bulk evaluation.

### A18 — Evidence Bundle

Add:

- image/hash/manifest generation time;
- waveform bundle scaling;
- disk-write latency;
- atomic finalize latency;
- cancellation/partial-bundle cleanup latency;
- no GUI blocking while hashing/writing large artifacts.

### A20 — Measurement Trend Dashboard

Add:

- sample received → model update;
- model update → rendered frame;
- p95 GUI heartbeat latency during plotting;
- scaling at 1k/10k/100k samples;
- bounded-memory behavior;
- decimation performance;
- no progressive frame-latency growth.

### A21 — Scientific Export

Add:

- samples/second;
- MB/s;
- export time at multiple record sizes;
- import/round-trip time;
- memory peak during export;
- GUI heartbeat during export.

### A25 — Headless Job Runner

Add:

- CLI startup latency;
- validation-only latency;
- first instrument-operation latency;
- total recipe overhead compared with direct sequencer execution;
- Ctrl-C/cancel latency;
- shutdown/session cleanup latency.

---

## 15. Feature completion gate

For A14/A15/A16/A18/A20/A21/A25, a feature is complete only when all applicable conditions are true:

1. Existing functional snapshots remain unchanged unless intentionally reviewed.
2. Boundary, min/max, negative and malformed-input tests pass.
3. Invalid input generates zero unintended instrument I/O.
4. Exact SCPI/query contract tests pass.
5. Fake-instrument error/timeout/reconnect tests pass.
6. GUI integration tests pass.
7. Deterministic timeout/retry/cadence tests pass.
8. Candidate p95/p99 performance is within its regression budget.
9. GUI responsiveness remains within its budget.
10. Queue depth and record age remain bounded at qualified sustained load.
11. Cancellation/reconnect/shutdown timing remains within budget.
12. Applicable DPO4054 functional HIL passes.
13. Applicable USB/TCPIP timing HIL passes.
14. No new progressive memory/thread/FD/performance growth is introduced.
15. Documentation and feature matrix are updated.
16. Only then may development continue to the next feature.

---

## 16. Regression invariant

The project regression invariant is:

> A new feature may add behavior, but it must not silently change established functional behavior, timing semantics, responsiveness, sustainable throughput, scheduling accuracy, recovery latency, or long-duration stability.

A candidate can therefore fail regression even when every final value is numerically correct.

Examples of valid regression failures include:

- GUI still works but freezes for 2 s during capture;
- logger writes all records but throughput falls by 5×;
- periodic logger slowly drifts from its requested interval;
- reconnect succeeds but takes 30 s instead of the established baseline;
- waveform acquisition is correct but 1M-point processing becomes O(n²);
- soak completes without exceptions but cycle p95 rises steadily for 24 h;
- cancellation eventually succeeds but the application remains blocked for several seconds;
- evidence bundle is correct but hashing runs synchronously on the GUI thread.

These are regressions and must block feature completion.
