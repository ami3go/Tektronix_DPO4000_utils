# A22 Live Waveform Streaming

## Status and baseline

The original bounded single-channel engine is merged. A22.1 extends it with a
first-class four-channel Live workspace. Exact-head USB/TCPIP four-channel HIL and
the release soak remain qualification gates.

**This is repeated public waveform transfer from oscilloscope acquisition memory,
not lossless access to the ADC stream.** Sustained FPS is bounded by the DPO4054,
transport, transfer length and host.

## Components

- `dpo4000_utils.live_stream.StreamConfig`: immutable, validated ordered selection
  of one to four channels; 10k samples/channel, 5 groups/s and 2k render points/channel
  are the GUI defaults.
- `LiveStreamEngine`: GUI-independent state, generation tokens, one outstanding
  acquisition lease, absolute monotonic deadlines, observable frame replacement.
- `capture_group(scope, ...)`: consumes **only** public
  `scope.read_channel_waveform_data(channel, point_count=...)` calls on the existing
  serialized worker, validates alignment, and returns no partial group.
- `minmax_indices`: O(N) bucket extrema with first/last endpoints. The worker
  prepares at most the configured render budget; the GUI never converts 1M
  samples into a million Python floats.
- `LiveWaveformPanel`: controls in the dedicated top-level Live page, with a
  one-shot acquisition timer and 100 ms / 10 FPS render timer.
- `LiveWaveformPlot`: large central shared-axis canvas with a scope-style graticule,
  CH1 yellow / CH2 cyan / CH3 magenta / CH4 green, labels and visible skew.

`WaveformFrame` and the atomic `WaveformGroup` are frozen and their render traces
comprise tuples. Individual frames retain acquisition timing so sequential capture
skew is measurable rather than presented as simultaneity.
The contained public `WaveformData` has a mutable compact `array`; ownership
is transferred without mutation after the worker returns. Consumers **must not**
alter `waveform.samples`.

### Scheduler and states

```text
IDLE -> STARTING -> RUNNING -> PAUSED -> STARTING -> RUNNING
                      |                    |
                      +-------> ERROR <----+
STARTING/RUNNING/PAUSED/ERROR -> IDLE via Stop
ERROR -> STARTING via user Start
```

A single acquisition dispatch is allowed per engine lease. Deadlines are
absolute monotonic times (`t0 + n * 1/rate`). If a transfer completes after
one or more deadlines, those deadlines are counted as `deadlines_skipped`;
there is never a backlog of catch-up transfers. Requested Hz is not claimed
as achieved acquisition FPS.

### Backpressure and generation

An in-flight group and one pending complete group are the effective maximum,
regardless of configured capacity 1–8. This deliberately implements a stricter
latest-only policy. A newer unrendered frame replaces the previous frame and
increments `frames_replaced`; `frames_rendered` increments only when the GUI
takes a pending frame on its independent 10 FPS timer. Replacement is
intentional and disclosed.

Every Start/Stop/Pause/Resume updates a monotonic generation. On completion,
the engine releases the physical in-flight lease *and* checks generation
before allowing an old frame or error to affect state. Start while a
previous generation is still physically in flight cannot submit a new
acquisition until the old callback releases the lease.

### Stop, Pause, errors, shutdown

Stop disables scheduling immediately, clears the pending frame and invalidates
old callbacks. The shared session lease is retained until an outstanding callback
returns, including after a Stop or shutdown request. The instrument's current
PyVISA call cannot be interrupted
reliably; actual release is bounded by the driver/VISA timeout. The GUI stays
responsive in the meantime. Pause also invalidates an in-flight result and
keeps the already drawn plot. Resume uses a new monotonic schedule; no replay.

The v1 error policy is **fail-fast** (persistent failure moves to ERROR);
automatic reconnect is not enabled and `reconnect=True` raises a configuration
error. The operator may manually Start again once the transport is ready.
Transport errors are still handled by the pre-existing persistent scope worker.

The composed feature surface enforces an A22 instrument lease at its shared
action dispatcher: recipe, evidence, export, automation and other scope
operations are rejected with a reason while A22 is active. Local operations
requiring no instrument I/O are unaffected. Closing the Desk stops the A22
timers and invalidates generations before normal serialized session teardown.

### Plot and memory

The render budget can be 500/1k/2k/5k/10k. Extrema and endpoints are preserved. When the scientific/PySide6 extra provides NumPy, min/max buckets are computed over zero-copy array views; a GUI-independent pure-Python fallback remains available.
The plot auto-scales both axes and paints only bounded prepared points on resize.

At 1M points with 16-bit samples, raw storage is about 2 MB per channel or 8 MB
for four channels. At most one pending and one in-flight group may coexist along
the acquisition/GUI boundary, or about 16 MB raw at that extreme, plus transient
driver/Qt transport objects and up to 10k render coordinates per channel. The
underlying PyVISA decoder may create additional transient allocations.
RSS/tracemalloc measurements in hosted synthetic benchmarks do not bound
third-party VISA library allocations. No A20 scalar history of waveforms
is constructed.

### Limitations and deferred

- Four-channel software behavior is implemented; exact-head physical USB/TCPIP
  qualification remains pending.
- Live View has no transfer-size selector: each channel is read exactly as the scope is set up (its record length, as reported by `WFMOUTPRE:NR_PT?`). The driver checks that count before `CURVE?` and rejects a record above 1M samples, so an oversized record never reaches the VISA buffer; reduce the scope record length instead. A fixed `point_count` is still accepted by the Qt-independent `StreamConfig` (capped at 1M).
- `Maximum` uses the 100 Hz software scheduling bound, not a guaranteed rate.
- Automatic reconnect, genuinely simultaneous acquisition access, stream
  recording/A18 evidence-per-group and WebSocket publishing are deferred.
- A22 uses the same session worker, so active conflicting workflows cannot run
  simultaneously. A future dedicated exclusive ownership service could
  further formalize cross-process arbitration.

## Validation

```bash
QT_QPA_PLATFORM=offscreen pytest -q tests/test_a22_*.py
python scripts/benchmark_a22_live_stream.py --output a22-synthetic-benchmark.json
```

Real DPO4054 HIL **writes** DATA:SOURCE/START/STOP/WIDTH/ENCDG via the public driver. It is not read-only. The operator must explicitly authorize reversible writes, reserve exclusive use of the scope and approve snapshot/verified restoration of all five DATA settings. The test restores these settings even when an acquisition fails; restoration failure is a hard hardware-safety gate.

Real DPO4054 HIL is opt-in:

```bash
DPO4000_HARDWARE=1 \
DPO4000_A22_REVERSIBLE_WRITES=YES \
DPO4000_A22_EXCLUSIVE=YES \
DPO4000_A22_RESTORE_APPROVED=YES \
DPO4000_RESOURCE='USB0::...::INSTR' \
DPO4000_EXPECT_IDN='TEKTRONIX,DPO4054' \
DPO4000_A22_RUN_SECONDS=30 \
DPO4000_A22_EVIDENCE_DIR=artifacts/a22-usb \
pytest -q -m hardware tests/hardware/test_a22_live_stream_hardware.py
```

Run only with an operator-verified DPO4054, safe bench setup and a proven restoration procedure. The HIL JSON includes RSS and Python allocation metrics and a separate DATA setup-restoration report. A Python-only HIL test does **not** measure GUI heartbeat, trigger fault-injection, or shared-session interference; those gates require additional supervised GUI/HIL evidence.

Repeat independently for TCPIP/VXI-11. **No claim of HIL qualification
is made until the real run completes and evidence is retained.** Use 10k/5 Hz
for an independently timed 30–60 minute bench soak after the short gates.

See [A22 test matrix](a22-test-matrix.md).
