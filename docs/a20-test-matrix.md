# A20 Measurement Trend Dashboard Test Matrix

| Area | Required cases |
|---|---|
| Model validation | bad capacity, bad series name, wrong type, NaN, +Inf, -Inf |
| Capacity | exact capacity, rollover, explicit drop count, clear/reset |
| Timestamp | monotonic accepted, backwards timestamp rejected |
| Multi-series | independent storage, common batch timestamp, bounded series count |
| Batch atomicity | invalid value does not partially append valid siblings |
| Decimation | under-budget passthrough, first/last preserved, spike/dip preserved, <= render budget |
| Scaling | 1k / 10k / 100k samples, bounded output size |
| Backpressure | one worker poll in flight, later timer ticks skipped/counted |
| GUI boundary | public `read_measurement_value()` only; no raw VISA/SCPI |
| GUI lifecycle | Start / Stop / Clear; capacity reset; interval change while running |
| Packaging | Linux and Windows Desk `--startup-check` |
| HIL | read-only active MEAS values -> bounded trend model |
| Controlled performance | model update latency, render latency, GUI heartbeat, decimation, memory trend |

## Regression gate

Before A20 is ready to integrate:

1. `pytest -q` passes on Python 3.10–3.13.
2. Ruff passes.
3. Full PySide6 offscreen suite passes.
4. Linux and Windows packaged Desk startup checks pass.
5. Synthetic 1k/10k/100k trend benchmark passes without output-growth violations.
6. Self-hosted DPO4054 integration runs when an active finite measurement is available.
7. Controlled-runner p50/p95/p99 and GUI-heartbeat results are reviewed separately from shared-runner smoke data.
