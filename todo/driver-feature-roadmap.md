# DPO4000 Utils — Post-R0 Driver / Application TODO

> **Roadmap status (2026-10-26):** This is the original execution checklist, not an up-to-date record of merged software. A14, A15, A16, A18, A20, A21, A22.1 four-channel Live View, A25 hardening, and P0 qualification guards are integrated (see the [README feature matrix](../README.md#full-feature-status-matrix)). Items are checked only where code or tests prove them; remaining hardware items need exact-head physical DPO4054 evidence, soak, or maintainer approval. The top-level "Overall sequence" boxes stay open until each feature's HIL and exit criteria are complete. Separately measured USB/TCPIP R0-T baselines and the reviewed 24-hour soak remain incomplete release gates. Do not check off any hardware gate without retained evidence.

This TODO is the implementation roadmap to follow **after the R0 functional and timing regression baseline is accepted**.

The rule for every stage is:

> Implement one feature area, run the full accumulated regression suite, run applicable DPO4054 HIL, and do not start the next stage until the current stage is green.

## Overall sequence

- [ ] **R0-F + R0-T — accept regression baseline**
- [ ] **A14 — Advanced Trigger**
- [ ] **A15 — Test Recipe / Sequencer**
- [ ] **A16 — Pass/Fail Rule Engine**
- [ ] **A18 — Evidence Bundle**
- [ ] **A20 — Measurement Trend Dashboard**
- [ ] **A21 — Scientific Export**
- [ ] **A25 — Headless Job Runner**

---

## R0-F + R0-T — Baseline gate

Purpose: establish the known-good functional and performance behavior before changing the driver.

- [ ] Make all regression tests OS-agnostic where practical.
- [x] Pass the software R0 regression batch on the development machine.
- [x] Pass GitHub CI on supported Python versions.
- [ ] Capture DPO4054 Probe Comp CH1 hardware baseline.
- [ ] Store separate TCPIP and USB performance baselines when both transports are available.
- [ ] Verify Automation/Logger HIL is fully green except intentional capability SKIPs.
- [ ] Verify exact scope setup restoration after HIL.
- [ ] Review and approve R0 functional snapshot changes explicitly.
- [ ] Review and approve R0 timing baseline changes explicitly.
- [x] Merge PR #29 only after all required checks are green.

Completion gate:

- [ ] R0 functional baseline accepted.
- [ ] R0 timing/performance baseline accepted.
- [ ] Real DPO4054 hardware baseline captured.

---

## A14 — Advanced Trigger

Purpose: extend trigger support beyond the existing basic edge-trigger path while preserving deterministic acquisition behavior.

### Driver/API

- [x] Define a normalized trigger configuration model.
- [x] Preserve existing edge-trigger API compatibility.
- [x] Add trigger readback API.
- [x] Add capability detection for trigger types/features instead of assuming support.
- [x] Normalize DPO4000 firmware abbreviations such as `ARM -> ARMED`, `SAV -> SAVE`, and `TRIG -> TRIGGER`.
- [x] Continue using `BUSY?`-based Single acquisition synchronization where supported.
- [x] Keep bounded acquisition timeout behavior.
- [x] Ensure temporary VISA timeout/session settings are always restored.
- [x] Reject malformed/non-finite/injection inputs before VISA I/O.
- [x] Separate structural validation from model/firmware capability validation.

### GUI

- [x] Add Advanced Trigger controls without breaking the current Trigger page.
- [ ] Disable or hide unsupported trigger options based on detected capability.
- [x] Preserve asynchronous GUI/worker boundaries.

### Regression / HIL

- [x] Add exact SCPI command-contract tests for each supported trigger mode.
- [x] Add unsupported-trigger tests.
- [ ] Add malformed reply / timeout / disconnect tests.
- [ ] Measure trigger configuration latency.
- [ ] Measure trigger readback latency.
- [ ] Measure Single arm-to-completion latency.
- [x] Verify timeout exactness and cancellation behavior.
- [x] Verify no unintended VISA timeout expansion.
- [x] Run full software regression batch.
- [ ] Run DPO4054 HIL and compare against R0 baseline.

Completion gate:

- [x] Existing regression suite green.
- [x] New A14 regression tests green.
- [ ] DPO4054 HIL green.
- [ ] No unreviewed R0 baseline regression.

---

## A15 — Test Recipe / Sequencer

Purpose: provide a reusable ordered test-execution engine independent of the GUI.

### Core engine

- [x] Define a versioned recipe schema.
- [x] Implement ordered step execution.
- [x] Support instrument configuration steps.
- [x] Support measurement/readback steps.
- [x] Support Single acquisition steps.
- [x] Support screenshot/image capture steps.
- [x] Support waveform capture/export steps.
- [x] Support deterministic Delay steps.
- [ ] Support conditional execution.
- [ ] Support loops/repeat counts with bounded limits.
- [x] Support retry/backoff policy.
- [x] Support pause/resume.
- [x] Support cancellation during delay and I/O.
- [x] Emit structured per-step result records.
- [x] Keep recipe engine independent of PySide/GUI classes.

### Scheduling

- [x] Use monotonic time for delays/timeouts.
- [ ] Avoid cumulative `work + sleep(interval)` drift.
- [ ] Define late-step/missed-deadline policy.
- [x] Bound retries and total execution where configured.

### GUI

- [x] Add recipe editor/load/save surface.
- [x] Add Run/Pause/Resume/Cancel controls.
- [x] Show current step and progress.
- [x] Keep all instrument work off the GUI thread.

### Regression / HIL

- [x] Add schema validation tests.
- [x] Add deterministic fake-clock delay tests.
- [x] Add cancellation tests.
- [x] Add retry/backoff timing tests.
- [x] Add large-recipe scalability test.
- [ ] Add scheduling drift/jitter tests.
- [x] Measure per-step dispatch overhead.
- [x] Measure total recipe execution overhead.
- [x] Run full accumulated regression suite.
- [ ] Run representative recipe on DPO4054 Probe Comp HIL.

Completion gate:

- [x] A14 + A15 tests green.
- [ ] Existing R0 baseline preserved within approved gates.
- [ ] Hardware recipe execution green.

---

## A16 — Pass/Fail Rule Engine

Purpose: evaluate measurement/test results against reusable engineering limits without coupling evaluation to the GUI.

### Core rules

- [x] Define a versioned rule schema.
- [x] Add numeric min/max/window comparisons.
- [x] Add equality/inequality comparisons where meaningful.
- [x] Add tolerance and percentage-window rules.
- [x] Add logical `AND` / `OR` / `NOT` composition.
- [x] Add missing/invalid measurement policy.
- [x] Return structured PASS / FAIL / ERROR result details.
- [ ] Preserve original measured value and units in evidence.
- [x] Keep rule evaluation side-effect free.

### Integration

- [x] Integrate rule evaluation into A15 recipes.
- [x] Expose rule results to GUI.
- [ ] Allow recipe branching based on rule outcome.

### Regression / performance

- [x] Add boundary-value rule tests.
- [x] Add NaN/Inf/missing-value tests.
- [x] Add nested logical-tree tests.
- [ ] Measure rules/second.
- [ ] Measure p95/p99 evaluation latency.
- [x] Test scaling with large rule trees.
- [ ] Verify no GUI-thread stalls during bulk evaluation.
- [x] Run full accumulated regression suite.

Completion gate:

- [x] Rule evaluation deterministic and fully tested.
- [x] R0/A14/A15 regressions remain green.

---

## A18 — Evidence Bundle

Purpose: produce one durable, auditable package containing all artifacts and metadata for a completed test/recipe.

### Bundle content

- [x] Define bundle schema/version.
- [x] Include structured test report (`JSON`).
- [ ] Include human-readable report (`Markdown` or equivalent).
- [x] Include manifest.
- [ ] Include scope IDN / firmware / resource transport.
- [ ] Include application/package version and commit SHA where available.
- [ ] Include recipe and rule definitions used for the run.
- [x] Include measurements and PASS/FAIL results.
- [x] Include screenshot(s) when requested.
- [x] Include waveform CSV / binary artifacts when requested.
- [ ] Include scope setup before/after where applicable.
- [ ] Include environment metadata.
- [x] Include SHA-256 hashes for evidence files.

### Reliability

- [x] Write into a temporary/incomplete bundle first.
- [x] Atomically finalize completed bundle.
- [x] Clean partial files on cancellation/failure according to policy.
- [ ] Avoid holding entire large waveform bundles in memory.
- [x] Keep hashing/file I/O off the GUI thread.

### Regression / performance

- [x] Test manifest consistency.
- [x] Test hash verification.
- [x] Test interrupted/partial bundle cleanup.
- [x] Test large-waveform bundle scaling.
- [x] Measure screenshot/hash/manifest generation time.
- [x] Measure disk-write and finalization latency.
- [ ] Verify GUI heartbeat remains responsive during bundle generation.
- [x] Run full accumulated regression suite.

Completion gate:

- [x] Evidence bundle is reproducible and auditable.
- [ ] No functional/performance regression outside approved gates.

---

## A20 — Measurement Trend Dashboard

Purpose: visualize and retain long-running measurement history without unbounded memory growth or GUI degradation.

### Data/model

- [x] Define timestamped trend sample model.
- [x] Support multiple measurement series.
- [x] Add bounded retention policy.
- [ ] Add optional disk-backed logging.
- [x] Add decimation/downsampling for large histories.
- [ ] Preserve source measurement units/metadata.

### GUI

- [x] Add live trend page/dashboard.
- [ ] Support pause/resume display without stopping acquisition.
- [ ] Support selectable time windows.
- [x] Keep plotting/update work bounded.

### Regression / performance

- [x] Test 1k samples.
- [x] Test 10k samples.
- [x] Test 100k samples.
- [x] Test bounded-memory behavior.
- [x] Measure sample-received to model-update latency.
- [ ] Measure model-update to rendered-frame latency.
- [ ] Track GUI heartbeat p50/p95/p99/max during plotting.
- [ ] Verify no progressive frame-latency growth.
- [x] Run full accumulated regression suite.

Completion gate:

- [ ] Trend rendering stays responsive and memory bounded.
- [x] Prior features remain green.

---

## A21 — Scientific Export

Purpose: provide robust engineering export suitable for Python/NumPy/Pandas/Jupyter and other scientific workflows.

### Export model

- [x] Define export metadata schema.
- [x] Preserve time-axis/scaling information.
- [x] Preserve source/channel/units/sample count.
- [ ] Preserve scope IDN and acquisition settings.
- [ ] Add structured measurement export.
- [x] Add waveform export suitable for direct numerical loading.
- [x] Keep current CSV compatibility where practical.
- [x] Consider NumPy/NPZ and/or another documented scientific format.
- [x] Add round-trip import validation utilities/tests.

### Scaling / performance

- [x] Test 1k-point waveform.
- [x] Test 10k-point waveform.
- [x] Test 100k-point waveform.
- [x] Test 1M-point waveform.
- [ ] Test largest practical/qualified DPO4054 record length.
- [x] Measure samples/second.
- [x] Measure MB/s.
- [x] Measure export and round-trip import time.
- [x] Record memory peak during export.
- [ ] Verify no accidental O(n^2) path.
- [ ] Verify GUI heartbeat during large export.
- [x] Run full accumulated regression suite.

Completion gate:

- [x] Export round-trip validated.
- [ ] Large-waveform performance within approved baseline gates.

---

## A25 — Headless Job Runner

Purpose: run recipes/tests without Qt for CI, Robot Framework, OpenTAP, lab automation, and remote/headless systems.

### CLI

- [x] Define stable CLI command and exit codes.
- [x] Accept VISA resource from command line/config.
- [x] Load A15 recipe files.
- [x] Load A16 rule definitions.
- [ ] Produce A18 evidence bundles.
- [x] Support output directory selection.
- [x] Support validation-only/dry-run mode.
- [x] Support deterministic Ctrl-C cancellation.
- [x] Always clean up VISA/session resources on exit.
- [x] Emit machine-readable JSON result.
- [ ] Emit concise human-readable console summary.

### Integration

- [x] Ensure CLI uses the same core sequencer/rule/evidence code as the GUI.
- [ ] Add examples for Robot Framework integration.
- [ ] Add examples for OpenTAP integration.
- [x] Keep GUI/PySide imports out of the headless execution path.

### Regression / performance

- [ ] Test CLI startup latency.
- [x] Test validation-only latency.
- [ ] Test first instrument-operation latency.
- [x] Compare total CLI recipe overhead with direct sequencer execution.
- [ ] Test Ctrl-C cancellation latency.
- [x] Test shutdown/session cleanup.
- [x] Test non-zero exit codes for FAIL / ERROR / invalid recipe.
- [ ] Run headless tests on Windows and Linux CI where supported.
- [ ] Run complete DPO4054 hardware recipe from CLI.
- [x] Run full accumulated regression suite.

Completion gate:

- [ ] Same recipe produces equivalent results in GUI and CLI.
- [ ] Headless execution is safe for unattended lab automation.

---

## Release qualification after architecture/features

For a normal release after these changes:

- [x] Full software regression suite green.
- [ ] OS-agnostic regression tests green on supported CI platforms.
- [ ] DPO4054 functional HIL green.
- [ ] TCPIP performance comparison against accepted R0 baseline green.
- [ ] USB performance comparison green when USB fixture is available.
- [ ] Automation/Logger HIL green.
- [ ] No unexpected functional snapshot changes.
- [ ] No unapproved p95/p99 performance regressions.
- [ ] 24-hour soak passes.
- [ ] Scope state restoration verified.
- [ ] Evidence/report artifacts retained for release qualification.

For major session/logger/architecture changes:

- [ ] Run 72-hour soak qualification.

---

## Development rules

- [ ] One major feature area per branch/PR.
- [ ] Add tests with the feature, not afterward.
- [ ] Never regenerate an R0 snapshot/baseline simply to make a test pass.
- [ ] Baseline changes require explicit technical justification and review.
- [ ] Driver/core code must remain usable without the GUI where practical.
- [ ] Hardware-changing HIL must save, restore, and verify scope configuration.
- [ ] Prefer capability detection/readback over undocumented assumptions.
- [ ] Keep VISA operations bounded and cancellable where practical.
- [ ] Keep expensive I/O and processing off the Qt GUI thread.
