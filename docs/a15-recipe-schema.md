# A15 recipe schema v1

A recipe is a JSON object with `version`, `name`, and `steps`. Version 1 allows at most 10,000 steps.

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
