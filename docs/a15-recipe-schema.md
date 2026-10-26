# A15 recipe schema v1 / v2

A recipe is a JSON object with `version`, `name`, and `steps`. A recipe may contain at most 10,000 steps after repeat blocks are expanded.

Version 1 contains only `call` and `delay` steps. Version 2 adds optional step `when` conditions and `repeat` blocks (see [Conditions and loops](#conditions-and-loops-v2)). Loading a version 1 document that uses v2 features is rejected; saving a recipe writes version 1 unless it uses v2 features, so existing documents and evidence definitions are unchanged.

Only two primitive step kinds are defined in A15:

- `call` — invoke a named, allowed public DPO4000 driver callable with validated positional/keyword arguments;
- `delay` — wait against an absolute monotonic deadline with bounded cancellation polling.

The format deliberately does not accept dotted/private Python attribute paths, embedded expressions, `eval`, imports, shell commands, or arbitrary code. It also blocks the public connection/session lifecycle methods and `probe_scpi_query`, so a recipe cannot bypass the worker-owned session boundary or smuggle an arbitrary SCPI query through the capability probe API.

## Call step

```json
{
  "kind": "call",
  "name": "Set CH1",
  "method": "configure_channel",
  "args": [
    {
      "channel": 1,
      "display": true,
      "scale": 0.5,
      "coupling": "DC"
    }
  ],
  "kwargs": {},
  "retry": {
    "attempts": 2,
    "delay_s": 0.1,
    "backoff": 2.0,
    "max_delay_s": 1.0
  }
}
```

For the public configuration methods, a JSON object used as the config argument is converted into the corresponding validated driver dataclass before the call is executed. Supported config conversions include channel, measurement, acquisition, A-trigger, B-trigger, display, math, reference, and bus configuration.

Before the first operation, the sequencer resolves every call and binds its arguments against the public method signature. A missing method or structurally invalid later call therefore fails the recipe before earlier instrument I/O occurs.

`attempts` includes the first call and is limited to 1..100. Retry waits are interruptible and use the sequencer's monotonic time source. `delay_s` and `max_delay_s` must be finite and non-negative; `backoff` must be finite and at least 1.

## Delay step

```json
{
  "kind": "delay",
  "name": "Settle",
  "seconds": 0.25
}
```

A Delay is measured against a monotonic deadline. Pause time is added to that deadline, so a 250 ms Delay still receives 250 ms of active delay time even if the recipe remains paused for several seconds. Cancellation is checked throughout the wait.

## Conditions and loops (v2)

### `when`

Any `call` or `delay` step may carry a condition. It uses the A16 compare operators and fields, with no expressions:

```json
{
  "kind": "call",
  "name": "High-range capture",
  "method": "read_screen_png",
  "when": {"input": "Vpp", "operator": ">=", "value": 2.0, "on_invalid": "fail"}
}
```

The optional A16 `unit` label (for example `"V"`) is accepted and recorded; like A16 it is a label only, with no conversion.

`input` names a value from a step that already ran: `<step name>`, `step.<name>` or `step.<index>`, plus dotted fields for dataclass/mapping values. For a repeated name, the most recent executed step wins. The step runs on PASS and is skipped on FAIL (recorded with `skipped: true`, zero attempts, no instrument I/O). Numeric instrument text, such as the `999.8784E+0` that `read_measurement_value` returns, is compared as a number (plain decimal or exponent notation only). The scope's `9.91E+37` "no valid measurement" value is never a number here: it is INVALID, as are `nan`/`inf` and any other text. INVALID (missing or non-numeric input) fails the run by default; `"on_invalid": "skip"` skips instead. Two steps with complementary conditions give if/else branching.

### `repeat`

```json
{
  "kind": "repeat",
  "name": "Re-read until settled",
  "count": 20,
  "steps": [
    {"kind": "delay", "name": "Settle", "seconds": 0.5, "when": {"input": "Vpp", "operator": "<", "value": 2.0}},
    {"kind": "call", "name": "Vpp", "method": "read_measurement_value", "args": [1],
     "when": {"input": "Vpp", "operator": "<", "value": 2.0}}
  ]
}
```

`count` is 1..10,000; blocks may nest up to 4 deep. Blocks are expanded into plain steps before execution, so preflight, the denied-method checks, the Desk results table and A25 all see every step. A `when` inside the block gives "repeat until": once the condition stops passing, the remaining iterations are skipped without I/O. Read the referenced value once before the loop so the first condition has an input.

## Execution states

`idle`, `running`, `paused`, `completed`, `cancelled`, `failed`.

A failed call stops the recipe. Cancellation prevents later steps from running. Step results record index, name, attempt count, start/finish monotonic timestamps, duration, and returned value in memory.

## Denied method names

The following public driver helpers are intentionally not recipe operations:

- `connect`
- `disconnect`
- `ensure_connected`
- `configure_session`
- `temporary_timeout`
- `probe_scpi_query`

Connection ownership remains with DPO4000 Desk's serialized worker/session gateway.
