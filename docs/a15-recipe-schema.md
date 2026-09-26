# A15 recipe schema v1

A recipe is a JSON object with `version`, `name`, and `steps`.

Only two primitive step kinds are defined in A15:

- `call` — invoke a named public callable on the DPO4000 driver object with validated positional/keyword arguments.
- `delay` — wait against an absolute monotonic deadline with bounded cancellation polling.

The recipe format deliberately does not accept raw SCPI strings, dotted/private Python attribute paths, embedded expressions, `eval`, imports, shell commands, or arbitrary code.

## Call step

```json
{
  "kind": "call",
  "name": "Enable CH1",
  "method": "set_channel_enabled",
  "args": [1, true],
  "kwargs": {},
  "retry": {
    "attempts": 2,
    "delay_s": 0.1,
    "backoff": 2.0,
    "max_delay_s": 1.0
  }
}
```

`attempts` includes the first call. Retry waits are interruptible and use the sequencer's monotonic time source.

## Delay step

```json
{
  "kind": "delay",
  "name": "Settle",
  "seconds": 0.25
}
```

A delay is measured from an absolute monotonic deadline and does not accumulate a fixed `work + sleep(interval)` drift.

## Execution states

`idle`, `running`, `paused`, `completed`, `cancelled`, `failed`.

A failed call stops the recipe. Cancellation prevents later steps from running. Step results record index, name, attempt count, start/finish monotonic timestamps, duration, and returned value in memory.
