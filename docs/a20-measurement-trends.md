# A20 Measurement Trend Dashboard

Status: implementation on `a20-measurement-trends`.

A20 adds bounded-memory live measurement trending without moving instrument I/O into the Qt GUI thread.

## Architecture

A20 has two layers:

1. `dpo4000_utils.trend` — framework-neutral bounded trend storage and min/max decimation.
2. `dpo4000_utils.gui_qt.composition.pages.trend` — Qt Measurement-page panel that polls selected MEAS slots asynchronously through the existing serialized scope worker.

The trend model owns no VISA, SCPI, Qt object, worker, or timer.

## Polling / backpressure

The dashboard polls selected `MEAS1..MEAS8` slots using public `read_measurement_value()` calls inside the existing `_run_action(..., retain_session=True)` worker boundary.

Only one poll may be in flight. If another timer tick arrives while a read is active, the tick is counted and skipped rather than enqueued. This prevents slow VISA reads from creating an unbounded request backlog.

Supported poll intervals:

- 250 ms
- 500 ms
- 1 s
- 2 s
- 5 s

A poll may contain multiple selected measurement slots; all returned finite values are appended with one common timestamp.

## Bounded model

`MeasurementTrendModel` stores each series in a fixed-size `deque`.

Default capacity: 100,000 samples per series.

Desk choices:

- 1,000
- 10,000
- 100,000 samples per series

Changing capacity explicitly clears the trend model so the memory contract is unambiguous.

The model records:

- current stored samples;
- total samples received;
- samples dropped because the capacity was full.

Input values and timestamps must be finite numbers. Timestamps are monotonic per series.

## Decimation

Rendering does not traverse every stored point when the series is large. `decimate_minmax()` partitions the interior samples into chronological buckets and emits each bucket's minimum and maximum in original time order while retaining the first and last points.

This preserves narrow peaks and dips better than simple stride sampling while keeping the rendered point count bounded.

Desk render budgets:

- 500
- 1,000
- 2,000
- 5,000 points per series

## GUI

A20 is attached to the existing Measurement page rather than creating a new top-level page.

Controls:

- MEAS1..MEAS8 selectors;
- poll interval;
- capacity;
- render-point budget;
- Start Trend;
- Stop;
- Clear.

Status shows:

- stored sample count;
- accepted poll batches;
- skipped timer ticks;
- last model-update duration;
- last scope-poll latency.

The painter receives already-decimated snapshots. Instrument I/O remains exclusively in the worker callback.

## Performance / regression

`scripts/benchmark_a20_trends.py` exercises 1k / 10k / 100k synthetic sample counts by default and records:

- append median duration;
- append samples/second;
- decimation median duration;
- peak traced Python memory.

Shared GitHub-hosted measurements are smoke evidence only. Authoritative A20 qualification still requires the controlled-runner metrics defined in `docs/regression-test-plan.md`:

- sample received -> model update;
- model update -> rendered frame;
- p95/p99 GUI heartbeat latency during plotting;
- 1k/10k/100k scaling;
- bounded-memory behavior;
- decimation performance;
- no progressive frame-latency growth.

## Hardware qualification

The focused DPO4054 test is read-only. It reads the existing MEAS1..MEAS8 setup/value snapshot and feeds any active finite measurements into the same bounded trend model. If the bench has no active finite measurement, the focused test reports a skip rather than modifying the scope solely to manufacture data.

## Definition of done

A20 software is complete when:

- bounded capacity and drop accounting are tested;
- invalid/non-finite values are rejected;
- batch validation does not silently corrupt existing series;
- min/max decimation stays within the render budget and preserves spikes;
- 100k sample scaling is covered;
- the Qt panel uses only the public driver API;
- one-in-flight poll backpressure is enforced;
- the full Python / Ruff / PySide6 / packaged-Desk matrix is green;
- the read-only DPO4054 integration test is available for the self-hosted runner.
