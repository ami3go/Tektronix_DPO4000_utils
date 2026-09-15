# R0-F / R0-T baselines

This directory holds the functional and timing/performance baselines required by
`docs/regression-test-plan.md` before A14 (Advanced Trigger) work begins.

## What R0-F and R0-T cover here

`docs/regression-test-plan.md` §3-4 defines a broad scope for both baselines. Most of it is
already satisfied by the existing 422-test pytest suite, pinned at a commit SHA rather than
duplicated as new golden files:

- Boundary/enum matrix, exact-SCPI-contract, and fake-instrument error/timeout tests
  (plan levels L0-L2) — e.g. `tests/test_control.py`, `tests/test_bus.py`,
  `tests/test_reference.py`.
- GUI contract snapshot (plan §3.5) — `tests/test_gui_qt_metadata.py`,
  `tests/test_gui_qt_channel_config_metadata.py`, `tests/test_gui_qt_status_bar_metadata.py`,
  `tests/test_gui_qt_collapsible_metadata.py`, `tests/test_gui_qt_composition_architecture.py`,
  and related `_metadata`/`_architecture` test modules — these already do Qt object/property
  inspection, not pixel screenshots.
- Automation A1-A12 and Logger functional behavior — `tests/test_automation_*.py`,
  `tests/test_logger_*.py` — software orchestration tests against fake VISA; a hardware
  snapshot adds nothing here.

The two JSON files in this directory cover what had **zero** existing artifacts:

- `r0_functional_baseline.json` — a real DPO4054 functional snapshot: normalized
  `get_*_configuration()`/`get_*_setup()` output for CH1-4, MATH, REF1-4, BUS1-4, MEAS1-8,
  trigger, horizontal, acquisition, display, plus a setup save/restore round-trip check.
- `r0_timing_baseline.json` — the first timing/performance distributions in this repo:
  min/p50/p95/p99/max/sample_count for connection, channel apply, measurement refresh,
  single acquisition, PNG capture, CSV export, and waveform acquisition scaled across
  multiple record lengths (samples/second included).

Both files carry a header with `schema_version`, `commit_sha`, `captured_at`,
`package_version`, `python`, `platform`, `resource`, `idn`, and `firmware` so a baseline is
always traceable to the exact code and instrument state it was captured against.

## Not yet covered

`r0_timing_baseline.json` includes an explicit `not_yet_covered` list rather than silently
implying full coverage. As of this baseline, the following require a fake-clock/Qt-heartbeat
test harness that doesn't exist yet and don't depend on hardware availability:

- worker dispatch / GUI callback latency
- core/full parameter refresh latency
- logger enqueue/write/drain throughput
- cancel/reconnect/shutdown latency
- GUI responsiveness under load (plan §7)
- concurrency/backpressure regression (plan §8)
- scheduler drift/jitter regression (plan §6)
- soak/long-duration stability (plan §12)

These are tracked as follow-up work, not part of this baseline.

## Regenerating

```bash
python scripts/capture_r0_baseline.py \
  --resource 'TCPIP0::192.168.0.5::INSTR' \
  --output-dir tests/baselines
```

Useful flags: `--test-channel`, `--reps-standard`, `--reps-heavy`, `--reps-waveform-large`,
`--waveform-sizes` (comma-separated point counts), `--skip-functional`, `--skip-timing`.

All write-capable steps (channel apply round-trip, record-length sweep, setup round-trip)
capture the original value first and restore it afterward — the same reversible
capture/act/restore discipline as `dpo4000_utils/hardware_verification_core.py`.

Per plan §11, USB and TCPIP/Ethernet timing are distinct baselines — don't compare numbers
captured over one transport against numbers captured over the other.

## Updating a baseline

Per the regression-test-plan invariant: baseline updates must be explicit and reviewed. Never
regenerate these files automatically just to make a failing regression comparison pass —
that defeats the point of having a baseline.
