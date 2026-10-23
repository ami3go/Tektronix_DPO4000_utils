# dpo4000-utils / DPO4000 Desk

`dpo4000-utils` is a Python driver, automation, test-sequencing, and scientific-data toolkit for Tektronix DPO4000-family oscilloscopes, developed around the DPO4054.

**DPO4000 Desk** is the project's single desktop GUI. It is implemented with **PySide6** and acts as a presentation/orchestration layer over the public `dpo4000_utils` driver API.

## Architecture

```text
PySide6 DPO4000 Desk
        |
        +-- composition controllers / serialized scope worker
        +-- A15 RecipeSequencer
        +-- A16 RuleEngine (local, no instrument I/O)
        +-- A21 Scientific Export (NPZ / DPOZ)
        |
        v
DPO4054 / DPO4000Scope public API
        |
        v
PyVISA / VISA backend / oscilloscope
```

The GUI must not own SCPI commands, access the raw `scope.scope` VISA handle, parse hardcopy payloads, or implement waveform/settings transfer logic. Instrument behavior belongs in the reusable driver API. A15 recipes execute validated public driver calls inside the existing serialized worker and cannot take over the VISA/session lifecycle or submit arbitrary SCPI. A16 rules are evaluated locally after recipe completion. A21 consumes public `WaveformData` objects and owns only scientific file serialization/import; it performs no VISA/SCPI operations itself.

See `docs/architecture.md`, `docs/a15-recipe-sequencer-plan.md`, `docs/a16-pass-fail-rules.md`, and `docs/a21-scientific-export.md`.

## Features

- PySide6 desktop application with Connection, Channels, Measurement, Trigger, Acquisition, Automation, Recipe, Logger, File, Display, and Log pages.
- USB/VISA and Ethernet VISA resources with a worker-owned retained session option.
- Advanced A-trigger configuration, verified time holdoff, and Sequence/B-trigger controls.
- A15 Test Recipe / Sequencer with versioned JSON recipes, validation, public-driver call steps, deterministic Delay steps, pause/resume/cancel, bounded retry/backoff, live step status, and timing results.
- A16 Pass/Fail Rule Engine with versioned JSON rule sets, `PASS` / `FAIL` / `INVALID`, numeric/range/delta operators, AND/OR/NOT rule trees, recipe-result inputs, and Desk rule-result presentation.
- A21 Scientific Export with lossless NumPy `.npz` and portable `.dpoz` archives, exact raw/preamble round-trip import, atomic file replacement, throughput metrics, and a File-page Desk panel.
- Automation and Logger workflows for unattended capture/logging with recovery, limits, retention, and run reporting.
- PNG screen capture with preview and clipboard copy.
- Enabled-channel waveform export to CSV.
- Scope setup save/restore through JSON.
- CH1..CH4 labels and full channel configuration.
- MATH waveform configuration.
- MEAS1..MEAS8 measurement management.
- Run/stop/single/continuous acquisition and force trigger.
- Acquisition mode, averaging, and record-length controls.
- Front-panel display intensity, persistence, and message controls.
- Full real-hardware public API qualification with Markdown/HTML/JSON evidence reports.
- Windows/Linux PyInstaller build and release helpers.

## Full feature status matrix

**Status snapshot:** 2026-10-23; assessed against the merged main branch and active feature PRs. This inventory distinguishes *software implemented* from *hardware qualified*. It is a point-in-time audit, not a dynamic CI dashboard.

| Status | Meaning |
|---|---|
| Implemented | Present on main; software-delivered, but not necessarily DPO4054-qualified |
| Partial | Some supported functionality is delivered, but defined limits or qualification remain |
| In progress | Present on an unmerged development branch / draft PR |
| Planned | Proposed or documented; not verified as implemented |
| Deferred | Deliberately not exposed pending hardware/protocol evidence |
| Qualification pending | Test machinery exists, but required retained hardware evidence is not verified complete |

**Release posture:** Python package version 0.9.0rc1; a release candidate, **not** the hardware-qualified stable 0.9.0. Hosted main-branch test and CodeQL workflows passed at baseline commit [8a5b6cf](https://github.com/ami3go/Tektronix_DPO4000_utils/commit/8a5b6cfcf794104a3f428799bd415874a8392d72). Hardware qualification requires independently recorded results, transport-specific baselines, and a reviewed 24-hour soak. Open draft branches [A22 #51](https://github.com/ami3go/Tektronix_DPO4000_utils/pull/51) and [A25 #50](https://github.com/ami3go/Tektronix_DPO4000_utils/pull/50) are not part of main until merged.

### Core driver / instrument control

| ID | Feature | Status | Implementation / limitation |
|---|---|---|---|
| D01 | USB VISA | Implemented | PyVISA resource support |
| D02 | Ethernet VISA | Implemented | VXI-11 / TCPIP resources and socket connection support |
| D03 | Resource discovery | Implemented | VISA enumeration and manual resource selection |
| D04 | Instrument identity | Implemented | Identity query/readback |
| D05 | Persistent session | Implemented | Single worker-owned retained connection |
| D06 | Per-operation session | Implemented | Compatible short-lived connection mode |
| D07 | Transport recovery | Implemented | Invalidate failed connection and reconnect under controlled policy |
| D08 | Error and timeout classification | Implemented | Stable exception types and scoped VISA-timeout restoration |
| D09 | SCPI argument safety | Implemented | Numeric, enum, string and single-message validation |
| D10 | CH1–CH4 controls | Implemented | Scale, position, offset, coupling, bandwidth, invert and probe gain |
| D11 | Channel labeling | Implemented | Read/write with safe quoting |
| D12 | MATH waveform configuration | Implemented | Display, definition, scale and position |
| D13 | REF channels | Implemented | Capability-dependent REF1–REF4 configuration |
| D14 | BUS configuration | Implemented | Capability-dependent BUS1–BUS4 configuration |
| D15 | Decoded BUS transactions | Partial | Extraction/logging is capability gated; physical decoder command path not fully qualified |
| D16 | MEAS1–MEAS8 | Implemented | Configure and read measurements |
| D17 | Basic edge trigger | Implemented | Source, slope, coupling, level and mode |
| D18 | Horizontal setup | Implemented | Position, scale and record length |
| D19 | Acquisition actions | Implemented | Run, Stop, Single and Force Trigger |
| D20 | Acquisition modes | Implemented | Supported sample, average and high-resolution modes |
| D21 | Acquisition completion | Implemented | Bounded synchronization and trigger-state normalization |
| D22 | Binary waveform transfer | Implemented | Structured raw samples and preamble validation |
| D23 | Long / partial waveform records | Implemented | Explicit range checking and full-record transfer |
| D24 | ASCII transfer | Implemented | Explicit compatibility/debug mode with size limits |
| D25 | Time/voltage scaling | Implemented | Correct outgoing preamble scaling |
| D26 | CSV waveform export | Implemented | Individual and combined source-qualified files |
| D27 | PNG capture | Implemented | Scope image, preview, clipboard and save |
| D28 | Setup files | Implemented | Validated JSON save/restore |
| D29 | Front-panel display | Implemented | Intensity, persistence and message controls |
| D30 | Staged refresh | Implemented | Core → REF → BUS with optional-feature isolation |

See [waveform API](docs/waveform-acquisition.md), [usage](docs/usage.md), and [driver implementation](dpo4000_utils/).

### DPO4000 Desk GUI

| Page / capability | Status | Delivered behavior |
|---|---|---|
| Connection | Implemented | Discovery, VISA connection, IDN, preferences |
| Channels | Implemented | CH1–CH4, MATH, REF and BUS setup |
| Measurement | Implemented | MEAS1–MEAS8 management and A20 trends |
| Trigger | Implemented | Basic and verified advanced A/B triggers |
| Acquisition | Implemented | Mode, record length, Run/Stop/Single |
| Automation | Implemented | Scheduled, triggered and conditional jobs |
| Recipe | Implemented | A15 sequencing and A16 rule evaluation |
| Logger | Implemented | Repeated-record logging, storage and health |
| File | Implemented | PNG, CSV, JSON and A21 scientific export |
| Display | Implemented | Front-panel controls |
| Log | Implemented | Application diagnostic output |
| Asynchronous worker | Implemented | Serialized scope calls off the Qt event loop |
| Lazy GUI page construction | Implemented | Composed window and page controllers |
| Connection/output preferences | Implemented | Persistent settings |
| Keyboard shortcuts | Implemented | Capture, acquisition and navigation |
| A22 live waveform plot | In progress | Implementation and tests on draft [PR #51](https://github.com/ami3go/Tektronix_DPO4000_utils/pull/51), not main |
| Remaining legacy GUI extraction | Planned | Incremental migration of compatibility implementation shims |

### Automation A1–A12

All twelve named automation features are software-delivered. Unattended 24-hour production qualification is a separate release gate.

| ID | Feature | Status | Delivered behavior |
|---|---|---|---|
| A1 | Periodic PNG | Implemented | Interval-based screen capture |
| A2 | Image on trigger | Implemented | Capture after acquisition completion |
| A3 | Image and CSV on trigger | Implemented | Coherent same-event evidence |
| A4 | Timed waveform logging | Implemented | Periodic full-record CSV |
| A5 | Measurement logger | Implemented | Timestamped measurement series |
| A6 | Conditional capture | Implemented | Threshold comparison, debounce, cooldown |
| A7 | Burst capture | Implemented | Finite repeated capture workflows |
| A8 | Duration/event limits | Implemented | Stop on configured boundaries |
| A9 | Retention | Implemented | Age/count/size constraints on owned files |
| A10 | Automation profiles | Implemented | Versioned JSON save/load |
| A11 | Automatic reconnect | Implemented | Transport retry and session recovery |
| A12 | Run report | Implemented | Event counts, failure information and stop reason |

See [automation backlog](docs/automation-feature-backlog.md).

### Logger L1–L14

| ID | Feature | Status | Delivered behavior / limitation |
|---|---|---|---|
| L1 | CH1–CH4 waveform logger | Implemented | Repeated analog records |
| L2 | MATH logger | Implemented | MATH source records |
| L3 | Waveform CSV | Implemented | Readable samples |
| L4 | Binary DPO4LOG | Implemented | Framed waveform/log data |
| L5 | Measurement logging | Implemented | Timestamped MEAS values |
| L6 | Decoded BUS events | Partial | Capability gated until decoder path is qualified |
| L7 | Mixed synchronized records | Implemented | Waveform/measurement with optional BUS data |
| L8 | Rotation | Implemented | Size/time/count policies |
| L9 | Retention | Implemented | Storage age/size/count controls |
| L10 | Automatic reconnect | Implemented | Transport recovery |
| L11 | Bounded buffering | Implemented | Producer/writer backpressure |
| L12 | Logger profiles | Implemented | Versioned settings |
| L13 | Runtime health | Implemented | Actual throughput, queue state and drops |
| L14 | Run report | Implemented | CSV/JSON reporting |
| — | DPO4LOG inspection CLI | Implemented | dpo4000-log utility |
| — | Real 24-hour soak | Qualification pending | Required final bench evidence |

See [Logger specification](docs/logger-tab-plan.md).

### A14 advanced trigger

| ID | Feature | Status | Limitation / completion condition |
|---|---|---|---|
| A14.1 | A-trigger type configuration | Implemented | Verified type selector |
| A14.2 | Pulse width | Implemented | Width limits, polarity, comparator |
| A14.3 | Runt | Implemented | Threshold and timing fields |
| A14.4 | LOGIC / setup-hold | Partial | Verified fields present; unmapped leaves withheld |
| A14.5 | Timeout | Implemented | Verified timeout trigger |
| A14.6 | Video | Partial | Verified fields exposed; unmapped leaf withheld |
| A14.7 | B-trigger / sequence | Implemented | Verified A/B constraints |
| A14.8 | Time holdoff | Implemented | Validated time-based holdoff |
| A14.9 | Advanced Trigger GUI | Implemented | Public-driver/worker boundary |
| A14.10 | Full DPO4054 HIL and R0-T | Qualification pending | Recorded live qualification and measured baselines |

See [A14 qualification backlog](docs/a14-advanced-trigger-backlog.md).

### A15–A25 recipes, rules, evidence, trends and export

| ID | Feature | Status | Delivered behavior |
|---|---|---|---|
| A15.1 | Versioned JSON recipes | Implemented | Validated v1 calls and delays |
| A15.2 | Ordered driver operations | Implemented | One serialized worker/session |
| A15.3 | Monotonic delays | Implemented | Deterministic time semantics |
| A15.4 | Bounded retries | Implemented | Backoff and per-step results |
| A15.5 | Pause/resume/cancel | Implemented | Cooperative interruption |
| A15.6 | Recipe GUI | Implemented | Load/save/validate/run/progress |
| A15.7 | Step timing | Implemented | Structured timing and attempts |
| A16.1 | Pass/fail engine | Implemented | PASS, FAIL and INVALID outcomes |
| A16.2 | Numeric/range/delta rules | Implemented | Bounded numeric comparisons |
| A16.3 | Compound logic | Implemented | AND, OR, NOT |
| A16.4 | Recipe-result inputs | Implemented | Values from A15 results |
| A16.5 | Rules in Desk | Implemented | Editor and results |
| A18.1 | Evidence bundle | Implemented | Atomic .dpoe with optional artifacts |
| A18.2 | SHA-256 verification | Implemented | Manifest integrity checking |
| A18.3 | Atomic archive finalization | Implemented | Safe replace/cleanup |
| A18.4 | Evidence GUI | Implemented | Bundle creation surface |
| A20.1 | Live measurement trends | Implemented | Selected MEAS inputs |
| A20.2 | Bounded trend model | Implemented | Per-series history capacity |
| A20.3 | Min/max decimation | Implemented | Peak-preserving display |
| A20.4 | Poll backpressure | Implemented | Single in-flight poll |
| A20.5 | Trend GUI | Implemented | Control and telemetry |
| A21.1 | Scientific NPZ | Implemented | NumPy-native export |
| A21.2 | Portable DPOZ | Implemented | Raw and CSV ZIP archive |
| A21.3 | Lossless import | Implemented | Exact sample/preamble round-trip |
| A21.4 | Archive safety | Implemented | Size, schema and member validation |
| A21.5 | Scientific export GUI | Implemented | File page and transfer metrics |
| A25.1 | Headless recipe runner | Implemented | dpo4000-job CLI |
| A25.2 | No-VISA validation | Implemented | --validate-only |
| A25.3 | Headless rules | Implemented | A16 evaluation |
| A25.4 | Headless NPZ/DPOZ | Implemented | Optional A21 export |
| A25.5 | Exit-code semantics | Implemented | Validation, runtime, recipe, rule, export, cancellation |
| A25.6 | JSON job reports | Implemented | Atomic output |
| A25.7 | Instrument identity guard | Implemented | Expected IDN checked before recipe |
| A25.8 | Ctrl-C cancellation | Implemented | Cooperative shutdown |
| A25.9 | Additional CLI hardening | In progress | Draft [PR #50](https://github.com/ami3go/Tektronix_DPO4000_utils/pull/50); final CI/HIL gates remain |

### A22 live waveform streaming

A22 is *repeated waveform record transfer*, not lossless continuous ADC sample streaming. Its implemented work is on draft [PR #51](https://github.com/ami3go/Tektronix_DPO4000_utils/pull/51), not main.

| Feature | Status | Current branch capability / limitation |
|---|---|---|
| Framework-neutral stream engine | In progress | Config, frame/state/stats models |
| CH1–CH4 source choice | In progress | One source at a time; additional channels await HIL |
| Simultaneous aligned multi-channel stream | Planned | Deliberately deferred |
| 1k/10k/100k/1M and Full | In progress | Limited by connected scope record size |
| Adjustable request cadence | In progress | Not a guaranteed delivered frame rate |
| Single in-flight acquisition | In progress | Shared worker lease |
| Latest-frame buffering | In progress | Drop/replace and missed-deadline accounting |
| Decimation and live plot | In progress | Worker-side peak preserving; bounded GUI rendering |
| Pause/Resume/Stop | In progress | Generation-token stale-callback protection |
| FPS, latency, throughput metrics | In progress | Stats and instrumentation |
| Automated software tests | In progress | PR adds engine, GUI heartbeat, scheduler and safety tests |
| HIL workflow and tests | In progress | Test infrastructure is present; live USB/TCPIP evidence pending |
| Automatic stream reconnect | Deferred | v1 fail-fast/manual restart policy |
| Per-frame A18/A21 recording | Deferred | Separate follow-up work |
| WebSocket/browser streaming | Planned | Remote streaming follow-on |

See [A22 plan](docs/a22-live-waveform-streaming-plan.md) and [draft implementation](https://github.com/ami3go/Tektronix_DPO4000_utils/tree/feat/a22-live-waveform-streaming).

### Verification, packaging and release

| Capability / gate | Status | Notes |
|---|---|---|
| Python unit and PySide6 regression | Implemented | Hosted CI suite, GUI tests |
| SCPI contract, fault-injection and security tests | Implemented | Deterministic software tests |
| R0-F functional comparison | Implemented | Baseline tooling and tests |
| R0-T timing/performance comparison | Implemented | Tools available; final hardware comparison pending |
| DPO4054 per-feature HIL modules | Implemented | Opt-in physical hardware tests |
| Automation/Logger HIL runner | Implemented | Bench tooling and reporting |
| Hardware soak runner | Implemented | Script exists; result is not implied |
| Final candidate hardware HIL | Qualification pending | Read-only/reversible/authorized profiles |
| USB and Ethernet performance baselines | Qualification pending | Separate measured hardware artifacts and review |
| 24-hour DPO4054 stability soak | Qualification pending | No claim of release acceptance without retained report |
| Hosted Tests and CodeQL | Implemented | Main-branch baseline checks passed |
| Windows/Linux and additional Linux packages | Implemented | Release build workflows |
| SBOM/checksums/attestation | Implemented | Release integrity tooling |
| Stable 0.9.0 publication gate | Qualification pending | Hardware, timing and soak must pass review |

### Planned, incomplete and deferred backlog

| Area | Remaining work | Status |
|---|---|---|
| A14 | BUS trigger field mapping | Deferred |
| A14 | Pulse TRANSITION trigger leaf mapping | Deferred |
| A14 | Remaining LOGIC/SETHOLD and video field qualification | Deferred |
| A14 | Holdoff-by-count/events | Deferred |
| BUS/Logger | Fully qualified decoded BUS extraction | Partial |
| A15 | Conditional execution and bounded loop/repeat blocks | Planned |
| A15/A16 | Branching driven by evaluated rules | Planned |
| A22 | Multi-channel alignment, reconnect, remote streaming | Planned/deferred |
| Qt architecture | Retire remaining compatibility window implementations | Planned |
| Qualification | Complete HIL, USB/TCPIP R0-T and long-duration soak | Pending |
| Release | Stable v0.9.0 after reviewed evidence | Pending |

The identifiers A13, A17, A19, A23 and A24 are not established as independently delivered milestones in the inspected roadmap; no implementation status is inferred from missing numbers.

### P0 completion priorities

| Priority | Workstream | Required exit evidence |
|---|---|---|
| P0 | Full DPO4054 hardware qualification | Signed/reviewed functional HIL results across relevant feature modules |
| P0 | USB and Ethernet R0-T baselines | Independent hardware measurements and regression comparisons for each transport |
| P0 | 24-hour stability soak | Retained 24-hour hardware run showing acceptable errors, GUI/worker behavior and no progressive resource growth |
| P0 | A25 PR #50 hardening and qualification | Full software/packaging gates, independent review, real hardware test, approved integration |

Feature completion and release approval must be based on retained evidence rather than the presence of tests or CI jobs alone. Test execution on a connected scope requires a controlled resource and the appropriate read-only or separately authorized reversible-write profile.

For details see [hardware qualification](docs/hardware-verification.md), [regression test plan](docs/regression-test-plan.md), [A25 CLI](docs/a25-headless-job-runner.md) and the [release gate](docs/releases/v0.9.0.md).

## Install

Minimum Python version:

```text
Python 3.10+
```

Driver/API only:

```bash
python -m pip install -e .
```

Driver plus scientific NPZ support without the GUI:

```bash
python -m pip install -e .[scientific]
```

Driver plus DPO4000 Desk (includes scientific NPZ support):

```bash
python -m pip install -e .[pyside6]
```

Development environment with the desktop GUI:

```bash
python -m pip install -e .[dev,pyside6]
```

Real instrument communication also requires a VISA runtime/backend such as NI-VISA, TekVISA, Keysight VISA, or another backend supported by PyVISA.

## Run DPO4000 Desk

```bash
dpo4000-desk
```

Or directly from a repository checkout:

```bash
python -m dpo4000_utils.gui_qt.runner
```

Useful shortcuts:

```text
F5              Capture preview
Ctrl+C          Copy preview after focusing the preview
Ctrl+S          Save PNG
Ctrl+Shift+S    Save CSV
F6              Run acquisition
F7              Stop acquisition
F8              Single acquisition
Ctrl+L          Focus VISA resource field
Ctrl+1..6       Connection through Automation pages
Ctrl+Shift+6    Recipe page
Ctrl+7          Logger page
Ctrl+8          File page
Ctrl+9          Display page
Ctrl+0          Log page
```

## A15 recipe example

Recipes are JSON and contain linear `call` and `delay` steps. Configuration mappings for public configuration methods are converted to their validated driver dataclasses before any instrument I/O.

```json
{
  "version": 1,
  "name": "Read trigger state",
  "steps": [
    {
      "kind": "call",
      "method": "get_trigger_configuration"
    },
    {
      "kind": "delay",
      "seconds": 0.1
    },
    {
      "kind": "call",
      "name": "HOLDOFF",
      "method": "get_trigger_holdoff"
    }
  ]
}
```

See `examples/a15_recipe_example.json` and `docs/a15-recipe-schema.md`.

## A16 pass/fail rule example

A16 consumes caller-provided scalars or values extracted from completed A15 steps. A unique A15 step name is available directly as a rule input, so the `HOLDOFF` step above can be checked without another scope query.

```json
{
  "version": 1,
  "name": "Holdoff sanity",
  "root": {
    "type": "compare",
    "id": "holdoff_non_negative",
    "input": "HOLDOFF",
    "operator": ">=",
    "value": 0.0
  }
}
```

Compound limits use `AND`, `OR`, and `NOT` groups. Invalid/missing/non-finite inputs return `INVALID` and never silently become `PASS`.

See `examples/a16_rules_example.json`, `docs/a16-pass-fail-rules.md`, and `docs/a16-test-matrix.md`.

## A21 scientific export example

A21 exports already-acquired `WaveformData`; the export module itself does not communicate with the instrument.

```python
from dpo4000_utils import (
    DPO4054,
    export_scientific_dataset,
    import_scientific_dataset,
)

with DPO4054("TCPIP0::192.168.0.5::INSTR", auto_connect=True) as scope:
    waveforms = scope.read_enabled_waveforms(point_count=100_000)

result = export_scientific_dataset(
    "capture.npz",
    waveforms,
    metadata={"test": "power-on transient"},
)
print(result.samples_per_second, result.megabytes_per_second)

loaded = import_scientific_dataset("capture.npz")
ch1 = loaded.dataset.by_source()["CH1"]
```

Use `.npz` for direct NumPy/Jupyter workflows. Use `.dpoz` for a portable ZIP containing manifest + exact raw samples + CSV traces. Both imports reconstruct the original waveform metadata and raw samples.

DPO4000 Desk exposes A21 under the existing **File** page with NPZ/DPOZ selection, full/1k/10k/100k/1M capture sizes, optional compression, and throughput reporting.

See `docs/a21-scientific-export.md` and `docs/a21-test-matrix.md`.

## Python API example

```python
from dpo4000_utils import AcquisitionConfig, ChannelConfig, DPO4054

with DPO4054(
    "USB0::0x0699::0x0401::C011280::INSTR",
    auto_connect=True,
) as scope:
    print(scope.query_identity())
    scope.configure_channel(
        ChannelConfig(channel=1, display=True, scale="0.5", coupling="DC")
    )
    scope.configure_acquisition(
        AcquisitionConfig(mode="AVERAGE", average_count=16, record_length="10k")
    )
    scope.save_image_path("scope_screen.png")
    scope.save_all_channels_to_single_csv("waveforms.csv")
```

A16 rule evaluation is independent of hardware:

```python
from dpo4000_utils import CompareOperator, RuleEngine, RuleSet, ScalarRule

rules = RuleSet(
    "5 V minimum",
    ScalarRule("vout_min", "MEAS1", CompareOperator.GTE, value=4.95),
)
result = RuleEngine().evaluate(rules, {"MEAS1": 5.01})
print(result.status.value)  # PASS
```

For frontend-style short-lived sessions:

```python
from dpo4000_utils import scope_session

with scope_session(
    "TCPIP0::192.168.1.50::INSTR",
    timeout_ms=20_000,
) as scope:
    print(scope.query_identity())
```

## Build executables

Windows:

```bat
scripts\build_windows_exe.bat
```

Linux:

```bash
chmod +x scripts/build_linux_executable.sh
./scripts/build_linux_executable.sh
```

See `docs/build-application.md` and `docs/build_executables.md` for packaging details.

## Tests

Core tests:

```bash
python -m pip install -e .[dev]
pytest -q
```

Full desktop test environment:

```bash
python -m pip install -e .[dev,pyside6]
QT_QPA_PLATFORM=offscreen pytest -q
```

Focused hardware pytest tests remain opt-in:

```bash
DPO4000_HARDWARE=1 \
DPO4000_RESOURCE='USB0::0x0699::0x0401::C011280::INSTR' \
pytest -q -m hardware tests/hardware
```

A15-focused DPO4054 qualification:

```bash
DPO4000_HARDWARE=1 \
DPO4000_ENABLE_WRITE_TESTS=1 \
DPO4000_RESOURCE='TCPIP0::192.168.0.5::INSTR' \
DPO4000_EXPECT_IDN='TEKTRONIX,DPO4054' \
pytest -q -m hardware tests/hardware/test_a15_recipe_hardware.py
```

A16 read-only DPO4054 integration qualification:

```bash
DPO4000_HARDWARE=1 \
DPO4000_RESOURCE='TCPIP0::192.168.0.5::INSTR' \
DPO4000_EXPECT_IDN='TEKTRONIX,DPO4054' \
pytest -q -m hardware tests/hardware/test_a16_rule_hardware.py
```

A21 DPO4054 scientific export qualification:

```bash
DPO4000_HARDWARE=1 \
DPO4000_RESOURCE='TCPIP0::192.168.0.5::INSTR' \
DPO4000_EXPECT_IDN='TEKTRONIX,DPO4054' \
pytest -q -m hardware tests/hardware/test_a21_scientific_export_hardware.py
```

A21 synthetic export/import benchmark:

```bash
python scripts/benchmark_a21_export.py \
  --sizes 1000,10000,100000,1000000 \
  --formats npz,dpoz \
  --output a21-export-benchmark.json
```

Capture the controlled A15 timing candidate with:

```bash
python scripts/capture_a15_recipe_baseline.py \
  --resource 'TCPIP0::192.168.0.5::INSTR' \
  --output a15_recipe_timing.json
```

## Full real-hardware qualification report

For release/bench qualification, use the self-auditing public API verifier. Start with the read-only profile:

```bash
python scripts/run_hardware_verification.py \
  --resource 'USB0::0x0699::0x0401::C011280::INSTR' \
  --profile read-only \
  --test-channel 1 \
  --waveform-points 1000
```

After the read-only run is clean, use `--profile reversible`, then `--profile full`. Write-capable profiles capture the initial scope setup and reapply it during final cleanup. Destructive REF waveform storage remains separately guarded and requires explicit overwrite authorization.

Each run generates Markdown, HTML, and JSON verification reports plus setup/screenshot/waveform evidence under `hardware_verification_reports/`.

See `docs/hardware-verification.md` for safety profiles, complete bench commands, exit-code semantics, waveform-size qualification, REF-overwrite handling, and self-hosted GitHub Actions usage.

## Repository layout

```text
dpo4000_utils/               reusable scope driver/API, recipe/rule engines, scientific exporter
dpo4000_utils/gui_qt/        PySide6 DPO4000 Desk application
 dpo4000_utils/gui/          framework-neutral GUI support helpers/assets
examples/                    driver/API, recipe, and rule examples
scripts/                     build, benchmark, baseline, packaging, and hardware-verification helpers
docs/                        documentation and GitHub Pages
tests/                       API, architecture, GUI, recipe, rule, export, and hardware tests
```

The former Tk frontend and its archived snapshots were removed in v0.4.0. `dpo4000-desk` is the only desktop application command.
