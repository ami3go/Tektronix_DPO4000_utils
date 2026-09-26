# A15 regression matrix

A15 uses the repository regression levels defined by `docs/regression-test-plan.md`.

| Level | A15 coverage |
|---|---|
| L0 validation | schema version, empty recipes, method identifiers, delay/retry numeric bounds, unknown fields |
| L1 contract | public method resolution and argument forwarding; no raw SCPI path |
| L2 fake instrument | deterministic failure, retry/backoff, stop-after-failure |
| L3 functional | stable recipe/result mapping and state transitions |
| L4 GUI | composition page controls and worker-action boundary |
| L5 timing | fake monotonic clock, absolute delay deadlines, bounded cancellation polling |
| L6 performance | per-step dispatch/large recipe benchmark to be captured by R0-T qualification |
| L7 concurrency | single sequencer run guard; no overlapping recipe run on one instance |
| L8 GUI responsiveness | execution delegated through existing asynchronous Desk action boundary |
| L9-L10 HIL | run reversible DPO4054 recipe and capture per-step/total timings |
| L11 soak | deferred to accumulated release qualification |

A15 is not considered hardware-qualified until the applicable L9/L10 measurements are captured on the DPO4054 runner. Software implementation and deterministic CI coverage are independent of that hardware gate.
