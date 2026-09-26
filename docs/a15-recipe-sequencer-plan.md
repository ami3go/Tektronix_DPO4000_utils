# A15 Test Recipe / Sequencer

Status: **software implementation complete; DPO4054 qualification pending**.

A15 adds a versioned test-recipe engine shared by DPO4000 Desk and the future A25 headless runner. Recipes execute only validated public driver operations through the existing serialized worker/session boundary. The GUI contains no direct VISA access and does not accept a raw-SCPI step.

## Delivered

- Stable JSON recipe schema v1 (`call` and `delay` primitives).
- Strict unknown-field, enum/type, finite-number, retry, step-count, and method-name validation.
- Whole-recipe method/signature preflight before the first operation, preventing a missing or malformed later call from leaving a partially applied recipe.
- Explicit denial of session/transport lifecycle methods and `probe_scpi_query`, which would otherwise provide a raw-SCPI escape hatch.
- JSON configuration coercion for the public configuration APIs (`ChannelConfig`, `MeasurementConfig`, `AcquisitionConfig`, `TriggerConfig`, `SequenceTriggerConfig`, `DisplayConfig`, `MathConfig`, `ReferenceConfig`, and `BusConfig`).
- Deterministic Delay steps using monotonic deadlines.
- Pause/resume where paused wall time does not consume the active Delay budget.
- Cooperative cancellation with bounded polling during Delay and retry backoff.
- Bounded retry/backoff policy (maximum 100 attempts).
- Single-run guard and stop-on-failure semantics.
- Ordered per-step result records with attempt count and duration.
- Recipe size guard (maximum 10,000 steps) and large-recipe non-recursive execution coverage.
- DPO4000 Desk top-level **Recipe** page with load, save, validate, run, pause, resume, cancel, live step status, and result timing.
- Recipe execution stays inside `_run_action(..., retain_session=True)`; the worker-owned scope instance is passed to the sequencer rather than fetched from GUI code.
- Existing page keyboard shortcuts are preserved; Recipe uses `Ctrl+Shift+6`.
- R0-T capture helper and CLI for recipe completion latency and per-step dispatch overhead.
- Opt-in DPO4054 HIL covering read-only execution, reversible holdoff execution, and A15 timing capture.

## Execution boundary

The Recipe page submits one serialized worker action. Inside that worker action the sequencer receives the already-owned public `DPO4000Scope` instance and executes recipe steps sequentially. There is no GUI-side scope loop and no direct `.scope`, `.query()`, `.write()`, or PyVISA access.

Pause/cancel are cooperative control signals. They take effect at sequencer checkpoints, Delay steps, and retry waits. An arbitrary blocking public driver method is not forcefully interrupted because doing so would violate the single-worker/session ownership model; instrument operations remain bounded by the driver's normal VISA timeout/cancellation behavior.

## JSON configuration calls

Configuration methods may receive their config as the first JSON argument. For example:

```json
{
  "kind": "call",
  "name": "Enable CH1",
  "method": "configure_channel",
  "args": [
    {
      "channel": 1,
      "display": true,
      "scale": 0.5,
      "coupling": "DC"
    }
  ]
}
```

The mapping is converted to the corresponding validated public dataclass before method signature preflight and before any instrument I/O.

## Qualification gate

A15 is not declared hardware-qualified until the self-hosted DPO4054 runner records:

1. read-only recipe execution on the real scope;
2. reversible write/readback/restore execution;
3. recipe completion p50/p95/p99 timing;
4. local per-step dispatch-overhead p50/p95/p99 timing on the controlled runner;
5. accumulated regression suite results with A14 still green.

The capture command is:

```bash
python scripts/capture_a15_recipe_baseline.py \
  --resource TCPIP0::192.168.0.5::INSTR \
  --output a15_recipe_timing.json
```

Measured timing values must come from the real qualification runner; they must not be synthesized or loosened merely to pass CI.
