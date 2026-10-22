# DPO4000 Utils — Post-R0 Driver / Application TODO

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
- [ ] Pass the software R0 regression batch on the development machine.
- [ ] Pass GitHub CI on supported Python versions.
- [ ] Capture DPO4054 Probe Comp CH1 hardware baseline.
- [ ] Store separate TCPIP and USB performance baselines when both transports are available.
- [ ] Verify Automation/Logger HIL is fully green except intentional capability SKIPs.
- [ ] Verify exact scope setup restoration after HIL.
- [ ] Review and approve R0 functional snapshot changes explicitly.
- [ ] Review and approve R0 timing baseline changes explicitly.
- [ ] Merge PR #29 only after all required checks are green.

Completion gate:

- [ ] R0 functional baseline accepted.
- [ ] R0 timing/performance baseline accepted.
- [ ] Real DPO4054 hardware baseline captured.

---

## A14 — Advanced Trigger

Purpose: extend trigger support beyond the existing basic edge-trigger path while preserving deterministic acquisition behavior.

### Driver/API

- [ ] Define a normalized trigger configuration model.
- [ ] Preserve existing edge-trigger API compatibility.
- [ ] Add trigger readback API.
- [ ] Add capability detection for trigger types/features instead of assuming support.
- [ ] Normalize DPO4000 firmware abbreviations such as `ARM -> ARMED`, `SAV -> SAVE`, and `TRIG -> TRIGGER`.
- [ ] Continue using `BUSY?`-based Single acquisition synchronization where supported.
- [ ] Keep bounded acquisition timeout behavior.
- [ ] Ensure temporary VISA timeout/session settings are always restored.
- [ ] Reject malformed/non-finite/injection inputs before VISA I/O.
- [ ] Separate structural validation from model/firmware capability validation.

### GUI

- [ ] Add Advanced Trigger controls without breaking the current Trigger page.
- [ ] Disable or hide unsupported trigger options based on detected capability.
- [ ] Preserve asynchronous GUI/worker boundaries.

### Regression / HIL

- [ ] Add exact SCPI command-contract tests for each supported trigger mode.
- [ ] Add unsupported-trigger tests.
- [ ] Add malformed reply / timeout / disconnect tests.
- [ ] Measure trigger configuration latency.
- [ ] Measure trigger readback latency.
- [ ] Measure Single arm-to-completion latency.
- [ ] Verify timeout exactness and cancellation behavior.
- [ ] Verify no unintended VISA timeout expansion.
- [ ] Run full software regression batch.
- [ ] Run DPO4054 HIL and compare against R0 baseline.

Completion gate:

- [ ] Existing regression suite green.
- [ ] New A14 regression tests green.
- [ ] DPO4054 HIL green.
- [ ] No unreviewed R0 baseline regression.

---

## A15 — Test Recipe / Sequencer

Purpose: provide a reusable ordered test-execution engine independent of the GUI.

### Core engine

- [ ] Define a versioned recipe schema.
- [ ] Implement ordered step execution.
- [ ] Support instrument configuration steps.
- [ ] Support measurement/readback steps.
- [ ] Support Single acquisition steps.
- [ ] Support screenshot/image capture steps.
- [ ] Support waveform capture/export steps.
- [ ] Support deterministic Delay steps.
- [ ] Support conditional execution.
- [ ] Support loops/repeat counts with bounded limits.
- [ ] Support retry/backoff policy.
- [ ] Support pause/resume.
- [ ] Support cancellation during delay and I/O.
- [ ] Emit structured per-step result records.
- [ ] Keep recipe engine independent of PySide/GUI classes.

### Scheduling

- [ ] Use monotonic time for delays/timeouts.
- [ ] Avoid cumulative `work + sleep(interval)` drift.
- [ ] Define late-step/missed-deadline policy.
- [ ] Bound retries and total execution where configured.

### GUI

- [ ] Add recipe editor/load/save surface.
- [ ] Add Run/Pause/Resume/Cancel controls.
- [ ] Show current step and progress.
- [ ] Keep all instrument work off the GUI thread.

### Regression / HIL

- [ ] Add schema validation tests.
- [ ] Add deterministic fake-clock delay tests.
- [ ] Add cancellation tests.
- [ ] Add retry/backoff timing tests.
- [ ] Add large-recipe scalability test.
- [ ] Add scheduling drift/jitter tests.
- [ ] Measure per-step dispatch overhead.
- [ ] Measure total recipe execution overhead.
- [ ] Run full accumulated regression suite.
- [ ] Run representative recipe on DPO4054 Probe Comp HIL.

Completion gate:

- [ ] A14 + A15 tests green.
- [ ] Existing R0 baseline preserved within approved gates.
- [ ] Hardware recipe execution green.

---

## A16 — Pass/Fail Rule Engine

Purpose: evaluate measurement/test results against reusable engineering limits without coupling evaluation to the GUI.

### Core rules

- [ ] Define a versioned rule schema.
- [ ] Add numeric min/max/window comparisons.
- [ ] Add equality/inequality comparisons where meaningful.
- [ ] Add tolerance and percentage-window rules.
- [ ] Add logical `AND` / `OR` / `NOT` composition.
- [ ] Add missing/invalid measurement policy.
- [ ] Return structured PASS / FAIL / ERROR result details.
- [ ] Preserve original measured value and units in evidence.
- [ ] Keep rule evaluation side-effect free.

### Integration

- [ ] Integrate rule evaluation into A15 recipes.
- [ ] Expose rule results to GUI.
- [ ] Allow recipe branching based on rule outcome.

### Regression / performance

- [ ] Add boundary-value rule tests.
- [ ] Add NaN/Inf/missing-value tests.
- [ ] Add nested logical-tree tests.
- [ ] Measure rules/second.
- [ ] Measure p95/p99 evaluation latency.
- [ ] Test scaling with large rule trees.
- [ ] Verify no GUI-thread stalls during bulk evaluation.
- [ ] Run full accumulated regression suite.

Completion gate:

- [ ] Rule evaluation deterministic and fully tested.
- [ ] R0/A14/A15 regressions remain green.

---

## A18 — Evidence Bundle

Purpose: produce one durable, auditable package containing all artifacts and metadata for a completed test/recipe.

### Bundle content

- [ ] Define bundle schema/version.
- [ ] Include structured test report (`JSON`).
- [ ] Include human-readable report (`Markdown` or equivalent).
- [ ] Include manifest.
- [ ] Include scope IDN / firmware / resource transport.
- [ ] Include application/package version and commit SHA where available.
- [ ] Include recipe and rule definitions used for the run.
- [ ] Include measurements and PASS/FAIL results.
- [ ] Include screenshot(s) when requested.
- [ ] Include waveform CSV / binary artifacts when requested.
- [ ] Include scope setup before/after where applicable.
- [ ] Include environment metadata.
- [ ] Include SHA-256 hashes for evidence files.

### Reliability

- [ ] Write into a temporary/incomplete bundle first.
- [ ] Atomically finalize completed bundle.
- [ ] Clean partial files on cancellation/failure according to policy.
- [ ] Avoid holding entire large waveform bundles in memory.
- [ ] Keep hashing/file I/O off the GUI thread.

### Regression / performance

- [ ] Test manifest consistency.
- [ ] Test hash verification.
- [ ] Test interrupted/partial bundle cleanup.
- [ ] Test large-waveform bundle scaling.
- [ ] Measure screenshot/hash/manifest generation time.
- [ ] Measure disk-write and finalization latency.
- [ ] Verify GUI heartbeat remains responsive during bundle generation.
- [ ] Run full accumulated regression suite.

Completion gate:

- [ ] Evidence bundle is reproducible and auditable.
- [ ] No functional/performance regression outside approved gates.

---

## A20 — Measurement Trend Dashboard

Purpose: visualize and retain long-running measurement history without unbounded memory growth or GUI degradation.

### Data/model

- [ ] Define timestamped trend sample model.
- [ ] Support multiple measurement series.
- [ ] Add bounded retention policy.
- [ ] Add optional disk-backed logging.
- [ ] Add decimation/downsampling for large histories.
- [ ] Preserve source measurement units/metadata.

### GUI

- [ ] Add live trend page/dashboard.
- [ ] Support pause/resume display without stopping acquisition.
- [ ] Support selectable time windows.
- [ ] Keep plotting/update work bounded.

### Regression / performance

- [ ] Test 1k samples.
- [ ] Test 10k samples.
- [ ] Test 100k samples.
- [ ] Test bounded-memory behavior.
- [ ] Measure sample-received to model-update latency.
- [ ] Measure model-update to rendered-frame latency.
- [ ] Track GUI heartbeat p50/p95/p99/max during plotting.
- [ ] Verify no progressive frame-latency growth.
- [ ] Run full accumulated regression suite.

Completion gate:

- [ ] Trend rendering stays responsive and memory bounded.
- [ ] Prior features remain green.

---

## A21 — Scientific Export

Purpose: provide robust engineering export suitable for Python/NumPy/Pandas/Jupyter and other scientific workflows.

### Export model

- [ ] Define export metadata schema.
- [ ] Preserve time-axis/scaling information.
- [ ] Preserve source/channel/units/sample count.
- [ ] Preserve scope IDN and acquisition settings.
- [ ] Add structured measurement export.
- [ ] Add waveform export suitable for direct numerical loading.
- [ ] Keep current CSV compatibility where practical.
- [ ] Consider NumPy/NPZ and/or another documented scientific format.
- [ ] Add round-trip import validation utilities/tests.

### Scaling / performance

- [ ] Test 1k-point waveform.
- [ ] Test 10k-point waveform.
- [ ] Test 100k-point waveform.
- [ ] Test 1M-point waveform.
- [ ] Test largest practical/qualified DPO4054 record length.
- [ ] Measure samples/second.
- [ ] Measure MB/s.
- [ ] Measure export and round-trip import time.
- [ ] Record memory peak during export.
- [ ] Verify no accidental O(n^2) path.
- [ ] Verify GUI heartbeat during large export.
- [ ] Run full accumulated regression suite.

Completion gate:

- [ ] Export round-trip validated.
- [ ] Large-waveform performance within approved baseline gates.

---

## A25 — Headless Job Runner

Purpose: run recipes/tests without Qt for CI, Robot Framework, OpenTAP, lab automation, and remote/headless systems.

### CLI

- [ ] Define stable CLI command and exit codes.
- [ ] Accept VISA resource from command line/config.
- [ ] Load A15 recipe files.
- [ ] Load A16 rule definitions.
- [ ] Produce A18 evidence bundles.
- [ ] Support output directory selection.
- [ ] Support validation-only/dry-run mode.
- [ ] Support deterministic Ctrl-C cancellation.
- [ ] Always clean up VISA/session resources on exit.
- [ ] Emit machine-readable JSON result.
- [ ] Emit concise human-readable console summary.

### Integration

- [ ] Ensure CLI uses the same core sequencer/rule/evidence code as the GUI.
- [ ] Add examples for Robot Framework integration.
- [ ] Add examples for OpenTAP integration.
- [ ] Keep GUI/PySide imports out of the headless execution path.

### Regression / performance

- [ ] Test CLI startup latency.
- [ ] Test validation-only latency.
- [ ] Test first instrument-operation latency.
- [ ] Compare total CLI recipe overhead with direct sequencer execution.
- [ ] Test Ctrl-C cancellation latency.
- [ ] Test shutdown/session cleanup.
- [ ] Test non-zero exit codes for FAIL / ERROR / invalid recipe.
- [ ] Run headless tests on Windows and Linux CI where supported.
- [ ] Run complete DPO4054 hardware recipe from CLI.
- [ ] Run full accumulated regression suite.

Completion gate:

- [ ] Same recipe produces equivalent results in GUI and CLI.
- [ ] Headless execution is safe for unattended lab automation.

---

## Release qualification after architecture/features

For a normal release after these changes:

- [ ] Full software regression suite green.
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
