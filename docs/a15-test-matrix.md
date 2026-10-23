# A15 regression matrix

A15 uses the repository regression levels defined by `docs/regression-test-plan.md`.

| Level | A15 coverage |
|---|---|
| L0 validation | schema version, empty/oversize recipes, public method identifiers, denied session/raw-probe methods, finite delay/retry bounds, unknown fields, JSON-value validation |
| L1 contract | whole-recipe method/signature preflight, argument forwarding, config-dataclass coercion, no raw SCPI path |
| L2 fake instrument | deterministic failure, bounded retry/backoff, retry cancellation, stop-after-failure, zero I/O on preflight failure |
| L3 functional | stable recipe/result mapping, state transitions, config mapping round trip |
| L4 GUI | composition Recipe page, canonical navigation entry, load/save/validate/run controls, worker-action boundary |
| L5 timing | fake monotonic clock, absolute Delay deadlines, pause-time compensation, bounded cancellation polling |
| L6 performance | `recipe_baseline.capture_recipe_timing()` records recipe-completion distribution and per-step dispatch overhead; measured controlled-runner values pending |
| L7 concurrency | single sequencer run guard; no overlapping recipe run on one instance |
| L8 GUI responsiveness | recipe execution delegated through existing asynchronous Desk action boundary; live progress returns through Qt signals |
| L9-L10 HIL | opt-in DPO4054 read-only recipe, reversible holdoff recipe, and R0-T timing capture implemented; live runner evidence pending |
| L11 soak | deferred to accumulated release qualification |

A15 software implementation is complete when normal CI is green. A15 is not considered hardware-qualified until the applicable L9/L10 measurements are captured on the DPO4054 runner and reviewed against the accumulated R0 baseline.
