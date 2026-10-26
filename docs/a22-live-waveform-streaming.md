# A22 Live Waveform Streaming

## Status and baseline

Implemented on development branch `feat/a22-live-waveform-streaming` from `main` at
`8a5b6cfcf794104a3f428799bd415874a8392d72`. All A14/A15/A16/A18/A20/A21/A25
feature PRs were merged before work began. Baseline hosted Tests workflow:
[39979418992](https://github.com/ami3go/Tektronix_DPO4000_utils/actions/runs/39979418992).

**This is repeated public waveform transfer from oscilloscope acquisition memory,
not lossless access to the ADC stream.** Sustained FPS is bounded by the DPO4054,
transport, transfer length and host.

## Components

- `dpo4000_utils.live_stream.StreamConfig`: immutable and fully validated request.
  Initial target CH1, 10k samples, 5 Hz, 2k render points, latest frame wins.
- `LiveStreamEngine`: GUI-independent state, generation tokens, one outstanding
  acquisition lease, absolute monotonic deadlines, observable frame replacement.
- `capture_frame(scope, ...)`: consumes **only**
  `scope.read_channel_waveform_data(channel, point_count=...)` on the existing
  serialized worker. Public waveform decoding/preamble validation is reused.
- `minmax_indices`: O(N) bucket extrema with first/last endpoints. The worker
  prepares at most the configured render budget; the GUI never converts 1M
  samples into a million Python floats.
- `LiveWaveformPanel`: attached to the existing Measurement page below A20,
  one-shot acquisition timer, 100 ms / 10 FPS render timer, bounded Qt painter.

The `WaveformFrame` dataclass is frozen and its render trace comprises tuples.
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

An in-flight frame and one pending complete frame are the effective maximum,
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

At 1M points with 16-bit samples, raw storage is about 2 MB per frame.
At most two complete frames may coexist along the acquisition/GUI boundary,
or ~4 MB raw, plus any transient driver/Qt transport objects and up to
10k tuples of render coordinates under the supplied GUI choices. The
underlying PyVISA decoder may create additional transient allocations.
RSS/tracemalloc measurements in hosted synthetic benchmarks do not bound
third-party VISA library allocations. No A20 scalar history of waveforms
is constructed.

### Limitations and deferred

- CH2–CH4 are selectable but require physical qualification.
- 1k/10k/100k/1M depend on the scope's configured record length. Unbounded Full transfer is deliberately **disabled**: a driver can allocate >1M points before an A22 post-transfer limit check. A bounded size request remains capped at 1M and oversized driver responses are rejected.
- `Maximum` uses the 100 Hz software scheduling bound, not a guaranteed rate.
- Automatic reconnect, multi-channel aligned concurrent acquisition,
  stream recording/A18 evidence-per-frame and WebSocket publishing are deferred.
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
