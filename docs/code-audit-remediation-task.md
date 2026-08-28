# DPO4000 Code Audit Remediation Task

Status: **Planned**  
Audit baseline: **v0.5.0**  
Repository: `ami3go/Tektronix_DPO4000_utils`  
Primary objective: move the driver and DPO4000 Desk from good engineering/lab quality to a production-grade implementation suitable for long-running automated test use.

## 1. Purpose

This document converts the v0.5.0 code audit into an implementation plan. It is intended to be executable by a developer or AI coding agent without repeating the audit.

The work must preserve existing public behavior where practical, but reliability and data integrity take priority over preserving implementation details. Breaking architectural changes must be isolated to minor-version milestones and documented.

## 2. Global engineering rules

Apply these rules to every phase.

1. Do not put raw VISA/SCPI access in PySide6 presentation code.
2. Public driver methods must own instrument communication, validation, timeout policy, and error translation.
3. Do not silently swallow transport failures. Optional/unsupported-command handling must be distinguishable from lost-session or timeout failures.
4. Every state-changing operation must either verify the result when practical or provide an explicit option to disable verification.
5. Every temporary VISA/session setting must be restored in `finally`, including timeout and terminations.
6. Cleanup must be exception-safe and must not hide the original operation failure.
7. Add unit/regression tests for every defect fixed.
8. Keep Python 3.10-3.13 CI green.
9. Keep the offscreen PySide6 runtime tests green.
10. For behavior that depends on real DPO4000 firmware, add/update hardware tests and document manual validation.
11. Any repository modification requires a version increment and changelog entry.
12. Do not combine the large waveform, persistent-session, and GUI-composition rewrites into one release.

## 3. Severity / release roadmap

| Phase | Target | Scope | Audit items |
|---|---|---|---|
| 1 | v0.5.1+ | Reliability foundation | lifecycle, cleanup, timeout restoration, typed errors, hardcopy state, settings validation, defaults |
| 2 | v0.5.2+ | Capability API | BUS/REF count discovery moved into public driver API |
| 3 | v0.5.3+ | SCPI command safety | numeric/enumeration validation and SCPI-injection prevention |
| 4 | v0.6.0 | Waveform subsystem | deterministic binary transfer, structured waveform data, CSV integrity |
| 5 | v0.7.0 | GUI instrument runtime | persistent worker-owned VISA session, no nested event loop |
| 6 | v0.8.0 | GUI architecture | flatten inheritance into composition/pages/controllers |

Version numbers are guidance. If intermediate defect releases are required, increment versions normally while keeping phase ordering.

---

# Phase 1 - Reliability foundation

## 4. Fix VISA disconnect / teardown safety

### Problem

`ConnectionMixin.disconnect()` closes the instrument and then the `ResourceManager`. If instrument close raises, the resource manager close may never run and internal references may remain populated.

### Files

- `dpo4000_utils/connection.py`
- `dpo4000_utils/session.py`
- connection/session tests

### Steps

1. Snapshot `self.scope` and `self.rm` into local variables.
2. Clear `self.scope` and `self.rm` before attempting external cleanup so object state cannot falsely report a live connection after a close failure.
3. Attempt scope close inside `try/except`.
4. Attempt resource-manager close in a separate `try/finally` path even if scope close failed.
5. Preserve the first cleanup exception for diagnostics.
6. If disconnect is called while handling another exception, do not replace the original operation exception with a secondary cleanup failure.
7. Ensure repeated `disconnect()` remains idempotent.
8. Ensure `scope_session()` uses the hardened disconnect path rather than duplicating cleanup logic.

### Tests

Add tests covering:

- normal close closes scope and RM exactly once;
- scope close raises but RM still closes;
- RM close raises after scope closes;
- repeated disconnect does not raise merely because resources are already cleared;
- context manager preserves a callback exception when cleanup also fails.

### Acceptance criteria

No failure in `scope.close()` can prevent an attempted `ResourceManager.close()`, and internal state always becomes disconnected.

---

## 5. Centralize temporary VISA attribute restoration

### Problem

Temporary timeout / termination code is duplicated. Some paths restore an attribute only when the previous value is not `None`, so a temporary value may remain installed.

### Files

- `dpo4000_utils/connection.py`
- `dpo4000_utils/hardcopy.py`
- `dpo4000_utils/settings.py`
- snapshot/capability code using temporary timeouts

### Steps

1. Add one driver-owned context manager for temporary VISA attributes, for example `temporary_session_attributes(...)`.
2. Capture whether each attribute exists and capture its exact original value.
3. Apply requested temporary values.
4. Restore every captured attribute in `finally`, including an original value of `None` where the backend accepts it.
5. If an attribute cannot be restored, log/raise a driver-specific diagnostic without hiding the primary operation error.
6. Replace duplicated timeout manipulation in optional capability reads, hardcopy, and setup restore with the shared helper.

### Tests

Cover original timeout values of integer, `None`, missing attribute, and attribute setter failure.

### Acceptance criteria

A driver operation never leaves a modified timeout/read termination/write termination after completion or failure.

---

## 6. Standardize public exception types

### Problem

The package defines `DPOError`, `DPOConnectionError`, `DPONotConnectedError`, `DPOImageCaptureError`, and `DPOSettingsError`, but public APIs frequently expose generic `ConnectionError`, `RuntimeError`, or backend exceptions.

### Files

- `dpo4000_utils/errors.py`
- `dpo4000_utils/connection.py`
- `dpo4000_utils/hardcopy.py`
- `dpo4000_utils/settings.py`
- public mixins

### Steps

1. Define the public exception contract in `errors.py`.
2. Add specific classes where useful, such as:
   - `DPOTransportError`
   - `DPOTimeoutError`
   - `DPOProtocolError`
   - `DPOCapabilityError` only if callers need it.
3. Translate PyVISA/backend failures at the driver boundary.
4. Preserve original exceptions using `raise ... from exc`.
5. Update GUI error handling to consume public driver exceptions rather than backend types.
6. Document which exceptions callers should catch for reconnect/retry behavior.

### Tests

Verify that connection loss, timeout, invalid image data, invalid settings payload, and not-connected operations expose stable package exceptions.

### Acceptance criteria

A caller can reliably implement reconnect/retry logic without importing PyVISA exception classes.

---

## 7. Separate unsupported optional commands from transport failures

### Problem

Several optional readers use broad `except Exception: return ""`. This can turn an unsupported command, USB disconnect, timeout, and programming defect into the same empty string.

### Files

- `dpo4000_utils/reference.py`
- `dpo4000_utils/bus.py`
- `dpo4000_utils/scope_snapshot.py`
- optional query helpers in control code

### Steps

1. Identify all broad exception handlers around instrument queries.
2. Define an explicit policy:
   - unsupported/optional field: record empty/unsupported and continue;
   - bounded timeout during optional feature discovery: circuit-break that optional section and record warning;
   - transport/session loss: propagate immediately;
   - unexpected Python/programming exception: propagate immediately.
3. Prefer PyVISA status/error inspection when available.
4. Keep staged snapshot failure isolation, but store a typed warning/error description in snapshot metadata.
5. Add tests proving a simulated lost session is not silently converted to an empty optional field.

### Acceptance criteria

Optional firmware differences remain non-fatal, but real connection failures are visible to the caller.

---

## 8. Make hardcopy capture state-safe

### Problem

Screen capture currently sends commands such as `*CLS`, `HEADER OFF`, `VERBOSE OFF`, and image-format settings without restoring all scope state. `*CLS` can also erase diagnostic/status evidence.

### Files

- `dpo4000_utils/hardcopy.py`
- hardcopy tests

### Steps

1. Determine the minimal DPO4000 commands required to capture PNG data.
2. Remove `*CLS` from normal hardcopy capture unless hardware testing proves it is required.
3. Read the current values of any persistent scope settings that will be changed.
4. Apply temporary hardcopy settings.
5. Capture and validate PNG bytes.
6. Restore the previous scope settings in `finally`.
7. Continue restoring VISA timeout and terminations through the shared session-attribute helper.
8. If firmware does not expose readback for a setting, document the limitation and minimize the changed state.

### Tests

- successful capture restores settings;
- failed binary read restores settings;
- invalid PNG restores settings;
- primary capture exception is not replaced by restoration failure.

### Hardware validation

Capture repeatedly on the real DPO4054 and verify subsequent normal SCPI responses and scope error state are unchanged except for unavoidable hardcopy behavior.

### Acceptance criteria

Taking a screenshot does not unexpectedly clear diagnostics or leave unrelated persistent communication/display settings changed.

---

## 9. Strengthen settings-file validation

### Problem

A restore file is largely accepted when it contains a non-empty `setup` string even though saved files also contain instrument and format metadata.

### Files

- `dpo4000_utils/settings.py`
- settings tests
- documentation

### Steps

1. Define a versioned settings payload schema.
2. Require/validate `setup_format` for new files.
3. Parse saved instrument identity into manufacturer/model/family where possible.
4. Before restore, query the connected instrument identity.
5. Reject clearly incompatible manufacturers/families.
6. For different but compatible DPO4000/MSO4000 models, warn or require an explicit compatibility override according to documented policy.
7. Validate type and size of the setup string.
8. Keep compatibility with existing older saved files through a documented legacy path.
9. Ensure corrupt JSON and malformed payloads raise `DPOSettingsError`.

### Acceptance criteria

The driver cannot silently apply an obviously incompatible or malformed settings payload.

---

## 10. Remove hardware-specific library defaults and constructor side effects

### Problem

The generic default VISA resource contains one physical scope serial number, `USB0::0x0699::0x0401::C011280::INSTR`. `DPO4000Scope` also defaults to `auto_connect=True` and creates `scope_settings/` during construction.

### Files

- `dpo4000_utils/connection.py`
- `dpo4000_utils/instrument.py`
- GUI preferences/defaults
- README/usage examples
- compatibility tests

### Steps

1. Introduce a neutral resource policy for the reusable driver.
2. Do not select one physical serial number as the library default.
3. Move lab-specific/default GUI resource selection into preferences or discovery.
4. Plan a compatibility-safe transition to `auto_connect=False` as the preferred constructor behavior.
5. Avoid creating filesystem directories in the instrument constructor.
6. Create settings/output directories only when a save operation actually requires them.
7. Update usage examples to explicitly connect or use `scope_session()`.
8. If preserving `visaResourceAddr` for backward compatibility, mark it deprecated and do not use it as the generic default long term.

### Acceptance criteria

Constructing a driver object does not require hardware and does not write to disk unless explicitly requested.

---

# Phase 2 - Capability-driven public API

## 11. Move BUS/REF capability discovery into the driver API

### Problem

Automatic snapshots correctly use `CONFIGURATION:BUSWAVEFORMS:NUMBUS?` and `CONFIGURATION:REFS:NUMREFS?`, but generic methods such as `get_all_bus_configurations()` still iterate hard-coded `BUS_SLOTS = (1, 2, 3, 4)`.

### Files

- `dpo4000_utils/bus.py`
- `dpo4000_utils/reference.py`
- `dpo4000_utils/scope_snapshot.py`
- GUI BUS/REF selector code

### Steps

1. Add public APIs such as:
   - `get_bus_waveform_count()`
   - `get_available_bus_slots()`
   - `get_reference_waveform_count()`
   - `get_available_reference_slots()`
2. Query Tektronix capability-count commands in the driver layer.
3. Implement bounded compatibility fallback for firmware that does not implement capability-count commands.
4. Make `get_all_bus_configurations()` enumerate the available bus slots, not the programmer-manual maximum.
5. Make `get_all_reference_configurations()` enumerate available reference slots.
6. Make `scope_snapshot.py` consume these public capability methods instead of duplicating Tektronix capability logic.
7. Make GUI selector population consume capability metadata/API results.
8. Preserve the existing no-BUS3/BUS4 timeout behavior on the real two-BUS DPO4054.

### Tests

- reported BUS count 2 => no BUS3/BUS4 traffic;
- reported REF count N => exactly N REF reads;
- capability query unsupported => bounded fallback;
- public `get_all_*` methods follow actual capabilities;
- GUI selector follows returned capability count.

### Hardware validation

Run against the DPO4054 and capture the command log proving BUS3/BUS4 are never queried when count=2.

### Acceptance criteria

Capability knowledge has one source of truth: the public driver API.

---

# Phase 3 - SCPI command safety and validation

## 12. Prevent raw user text from becoming unintended SCPI commands

### Problem

Several setters append user/editable strings directly to SCPI program messages. A value containing `;`, newline, or carriage return could form additional SCPI commands. Numeric invalid values are often delegated to the instrument instead of validated locally.

### Files

- `dpo4000_utils/control.py`
- `dpo4000_utils/bus.py`
- `dpo4000_utils/reference.py`
- any other command builders

### Steps

1. Inventory every command builder accepting `str | float | int`.
2. Split values into explicit categories:
   - numeric;
   - boolean;
   - enum/token;
   - quoted text;
   - expression fields where Tektronix syntax intentionally permits operators.
3. Numeric fields:
   - parse locally;
   - reject booleans where inappropriate;
   - reject NaN/Inf unless manual explicitly allows them;
   - format with deterministic numeric formatting.
4. Enum fields:
   - normalize case;
   - validate against allowed values/aliases.
5. Raw unquoted fields:
   - reject `;`, `\n`, `\r`, and other SCPI message separators.
6. Quoted text:
   - continue using a centralized safe quoting helper;
   - enforce documented length limits.
7. Expression fields such as MATH definitions must have a dedicated validation/escaping policy rather than using the generic numeric/token validator.
8. Add local validation ranges where the programmer manual defines stable device-family limits. Where valid ranges are model/mode dependent, validate syntax locally and let the scope validate range.
9. Do not silently truncate values except documented label limits; prefer clear validation errors where truncation could change meaning.

### Tests

For each public config type, add tests rejecting values such as:

- `"1;*RST"`
- `"1\n*RST"`
- `"nan"` where not allowed
- unsupported enum tokens
- invalid numeric text

Also verify legitimate engineering notation such as `1e-3` remains accepted where appropriate.

### Acceptance criteria

Editable GUI/API values cannot create a second unintended SCPI program message.

---

# Phase 4 - Waveform subsystem rewrite (v0.6.0)

## 13. Make waveform acquisition deterministic

### Problem

Current acquisition relies on inherited scope transfer state and does not explicitly configure `DATA:START`, `DATA:STOP`, and binary transfer width/encoding.

### Files

- `dpo4000_utils/waveform.py`
- waveform tests
- CSV API tests
- hardware tests

### Steps

1. Define an explicit waveform acquisition request model, for example:
   - source/channel;
   - start index;
   - stop index or point count;
   - encoding;
   - sample width.
2. Before `CURVE?`, explicitly configure:
   - `DATA:SOURCE`;
   - `DATA:START`;
   - `DATA:STOP`;
   - `DATA:WIDTH`;
   - binary encoding appropriate for DPO4000.
3. Read all scaling metadata required to interpret the transfer as one coherent transaction.
4. Prefer preamble read before the curve transfer when this preserves correspondence with the requested source/range.
5. Transfer binary IEEE-488.2 block data.
6. Decode signed/unsigned byte or word data according to preamble/encoding.
7. Scale samples using X/Y preamble values.
8. Validate received sample count against requested/declared point count.
9. Raise a waveform-specific/protocol exception on malformed blocks or inconsistent lengths.
10. Keep ASCII acquisition only as an explicit compatibility/debug option, not the default high-volume path.

### Hardware validation

Validate at several record lengths, including at least:

- 1k;
- 10k;
- 100k;
- the largest practical record length supported by the connected DPO4054/options.

Compare first/last timestamps, point count, and voltage scaling against scope readback/reference data.

### Acceptance criteria

The same acquisition request produces the same transfer range independent of previous front-panel/SCPI transfer configuration.

---

## 14. Introduce structured waveform data

### Problem

Waveform functions return separate Python lists and multi-channel export keys data by user label.

### Steps

1. Add a dataclass, for example `WaveformData`, containing:
   - source/channel;
   - label;
   - sample count;
   - X increment/origin/reference as needed;
   - Y multiplier/offset/zero as needed;
   - time values or sufficient metadata to generate them;
   - voltage/sample values;
   - acquisition timestamp if useful.
2. Return structured waveform objects from the new primary API.
3. Keep old tuple-returning methods as compatibility wrappers if necessary.
4. Avoid unnecessary duplicate full-size lists where possible for large records.
5. Document memory behavior for multi-million-point acquisition.

### Acceptance criteria

Waveform identity and metadata remain attached to the sample data throughout export and processing.

---

## 15. Prevent duplicate labels from overwriting channels

### Problem

Current multi-channel data uses `channel_data[label] = voltages`; duplicate CH labels silently replace earlier channels.

### Steps

1. Never use the editable label as the unique internal key.
2. Use channel/source identity as the primary key.
3. CSV headers should remain unique, for example:
   - `CH1 Voltage`
   - `CH2 Voltage`
4. Define deterministic handling of blank and duplicate labels.
5. Add regression tests with CH1 and CH2 both labeled `Voltage`.

### Acceptance criteria

No enabled channel can disappear from an export due to a duplicate label.

---

## 16. Validate multi-channel point alignment

### Problem

Combined CSV output assumes every channel has the same number of points/time positions as the first channel.

### Steps

1. Compare sample count and X-axis metadata for all channels.
2. If channels are expected to share the same acquisition basis, require equality and raise a clear error on mismatch.
3. If future hardware permits different axes, define an explicit resampling/export policy rather than indexing blindly.
4. Add tests for mismatched sample lengths.

### Acceptance criteria

CSV writing cannot index beyond a shorter channel or silently misalign channel data.

---

# Phase 5 - Persistent worker-owned VISA session (v0.7.0)

## 17. Replace one-session-per-button architecture

### Problem

Every GUI action currently opens a `ResourceManager`, opens a VISA resource, performs `*IDN?`, executes one operation, then closes everything. Parameter refresh uses multiple independent sessions.

### Target architecture

```text
PySide6 GUI
    |
    | queued commands/signals
    v
InstrumentController
    |
    v
Dedicated instrument QThread
    |
    v
ONE DPO4000Scope / VISA session
```

### Steps

1. Introduce an `InstrumentController`/worker object that owns exactly one `DPO4000Scope` while connected.
2. Move it to a dedicated `QThread`.
3. Expose queued requests/signals for connect, disconnect, read, write/configure, snapshot, image capture, and waveform acquisition.
4. Serialize instrument operations through the one worker.
5. Keep all QWidget access on the GUI thread.
6. On connect:
   - open resource;
   - apply timeout/termination;
   - query/validate IDN;
   - retain the session.
7. On user operation, reuse the retained session.
8. On disconnect/window close, stop accepting new work and close the worker-owned session.
9. Implement a defined recovery path for lost USB/VXI-11 connection.
10. Ensure switching resource/protocol performs clean disconnect then reconnect.

### Acceptance criteria

Repeated GUI actions do not repeatedly create VISA ResourceManagers/sessions.

---

## 18. Remove nested `QEventLoop`

### Problem

`_run_action()` uses a worker thread but synchronously waits through a nested `QEventLoop`, allowing re-entrant Qt event processing and complicating close/cancel behavior.

### Steps

1. Replace synchronous `_run_action()` return flow with asynchronous completion signals/callback handlers.
2. Each action should have:
   - request;
   - busy state;
   - result handler;
   - error handler;
   - final UI-state handler.
3. Disable or queue instrument controls while an operation that must be exclusive is active.
4. Do not start overlapping instrument transactions on the same session.
5. Remove nested `QEventLoop.exec()` from production instrument paths.
6. Keep progress/status updates non-modal where appropriate.

### Tests

- action completion updates widgets;
- error resets busy state;
- second action cannot overlap illegally;
- UI remains responsive during a simulated long VISA call;
- no nested event loop is used by the final launch path.

### Acceptance criteria

Production GUI instrument actions are genuinely asynchronous and non-reentrant.

---

## 19. Add cancellation and safe window-close semantics

### Steps

1. Define which operations can be cancelled and which can only be allowed to time out.
2. On application close:
   - prevent new requests;
   - request worker shutdown;
   - abort/close VISA safely where backend permits;
   - wait for thread shutdown without indefinite GUI hang.
3. Make close behavior safe during image transfer, waveform transfer, settings restore, and parameter refresh.
4. Add tests using delayed fake workers/sessions.

### Acceptance criteria

Closing the application during an active instrument operation does not leave a worker thread/session alive or crash Qt.

---

## 20. Make full parameter refresh a coherent session snapshot

### Steps

1. Retain staged readers (core -> REF -> BUS) for fault isolation.
2. Execute all stages through the same already-connected worker session.
3. Apply core results to the GUI immediately while optional stages continue.
4. Preserve capability-driven REF/BUS limits.
5. Timestamp the overall snapshot and optionally individual stages.

### Acceptance criteria

A full refresh no longer reconnects between stages and represents one continuous instrument session.

---

# Phase 6 - Flatten GUI architecture (v0.8.0)

## 21. Replace deep window inheritance with composition

### Problem

The launched Qt class is assembled through a long historical inheritance chain (`bus_window -> desktop_window -> api_window -> ... -> main_window`). This makes active method ownership difficult to reason about and leaves legacy raw-VISA code in ancestor classes.

### Target architecture

```text
MainWindow
  +-- ConnectionPage
  +-- ChannelsPage
  +-- MeasurementPage
  +-- TriggerPage
  +-- AcquisitionPage
  +-- SettingsPage
  +-- LogPage
  +-- InstrumentController
```

### Steps

1. Freeze current GUI behavior with runtime/interaction tests before refactoring.
2. Create independent page/widget classes with no instrument I/O.
3. Move UI-only helpers into shared Qt utility modules.
4. Move status/busy/instrument coordination into one application controller/main window layer.
5. Port one page at a time from the inheritance chain.
6. Remove superseded `experimental`, `practice`, `enhanced`, `stable`, and other historical window layers from the launch dependency graph.
7. Delete dead compatibility code only after tests prove the final entry point no longer depends on it.
8. Update architecture documentation and diagrams.

### Acceptance criteria

A developer can identify the active implementation of an action without resolving a multi-level Python MRO chain.

---

## 22. Strengthen architecture CI

### Problem

Current boundary tests mainly inspect a small set of final adapter files. Inherited GUI source still contains raw `scope.scope`, direct `.query()`/`.write()`, and raw transfer helpers.

### Steps

1. Define the allowed dependency direction:

```text
GUI widgets/pages
    -> application/controller API
    -> dpo4000_utils public driver API
    -> PyVISA
```

2. Add AST-based tests over the complete production `gui_qt` dependency set.
3. Forbid GUI production modules from:
   - importing `pyvisa`;
   - accessing `scope.scope`;
   - calling instrument `.query()`/`.write()`;
   - defining Tektronix SCPI command strings;
   - importing low-level raw transfer helpers.
4. If a temporary exception is required during migration, use a narrow explicit allowlist with a TODO/version-removal condition.
5. Add a test that resolves/imports the final launched `QtScopeWindow` and checks its instrument actions are controller/public-API based.

### Acceptance criteria

Architecture CI enforces the whole production GUI boundary rather than only selected final files.

---

# Cross-cutting release / maintainability work

## 23. Reproducible release dependencies

### Problem

Runtime/build extras allow floating dependency versions such as `PySide6>=6.7`, `pyvisa`, `pillow`, and `pyinstaller`. Rebuilding the same project release later may produce different binaries.

### Steps

1. Keep reasonable ranges in `pyproject.toml` for library consumers.
2. Add a release/test lock or constraints file generated from validated versions.
3. Make executable build workflows install from the release constraints.
4. Record Python, PySide6, PyVISA, Pillow, and PyInstaller versions in release artifacts/build logs.
5. Consider pinning GitHub Actions to immutable commit SHAs for release workflows.

### Acceptance criteria

A released executable can be rebuilt using the documented dependency set with materially identical dependency versions.

---

## 24. Logging and diagnostic cleanup

### Steps

1. Replace driver-layer `print()` with `logging` or returned data.
2. Remove `input()` interaction from non-CLI driver methods; overwrite decisions belong to the caller/GUI.
3. Add module-level logger names and useful structured context: resource, operation, channel/slot, timeout.
4. Never log binary waveform/image payloads by default.
5. Ensure diagnostics include chained backend exception information where useful.

### Acceptance criteria

The reusable driver is non-interactive and suitable for Robot Framework, OpenTAP, pytest, services, and unattended scripts.

---

## 25. Documentation cleanup

### Steps

1. Remove stale statements that the PySide6 GUI is experimental or that Tk remains available.
2. Update architecture documentation after each architectural milestone.
3. Document resource discovery and explicit connection lifecycle.
4. Document timeout behavior and reconnect policy.
5. Document waveform memory/performance expectations.
6. Document BUS/REF capability behavior and licensed/optional features.
7. Add a production-use example with `try/finally` or `with scope_session(...)`.

---

# 26. Required test strategy

Every phase must run the existing suite plus new tests.

## Unit tests

Cover pure validation/builders/parsers without hardware.

## Fake VISA integration tests

Use a deterministic fake instrument/resource manager to exercise:

- connect/disconnect lifecycle;
- timeout restoration;
- error translation;
- capability discovery;
- binary waveform parsing;
- cleanup on exceptions.

## PySide6 runtime tests

Use `QT_QPA_PLATFORM=offscreen` to cover:

- worker/controller lifecycle;
- busy-state gating;
- result/error projection;
- connection/disconnection;
- dynamic BUS/REF selectors;
- window close during active work.

## Hardware tests

Keep hardware tests opt-in with the `hardware` marker. Required milestone validations should include:

1. repeated connect/disconnect loop;
2. repeated IDN/control action loop;
3. repeated full parameter refresh;
4. PNG capture followed by normal SCPI/status checks;
5. BUS count/read on DPO4054;
6. REF read/store test where safe;
7. binary waveform acquisition at multiple record lengths;
8. settings save/restore round trip on a controlled setup.

---

# 27. 24/7 stability qualification gate

Do not label the implementation 24/7 production-ready until the following qualification exists.

1. Run an automated soak test for at least 24 hours; 72 hours is preferred.
2. Exercise a realistic operation mix:
   - IDN/status;
   - channel readback;
   - trigger/acquisition controls;
   - measurements;
   - snapshots;
   - periodic PNG capture;
   - periodic waveform capture/export.
3. Record:
   - operation count;
   - errors/timeouts;
   - reconnect count;
   - process RSS/private memory;
   - open file descriptors/handles where available;
   - worker/thread count;
   - VISA session open/close count.
4. Inject failures:
   - USB/Ethernet disconnect and reconnect;
   - timeout;
   - unsupported optional command;
   - malformed/partial fake binary response in automated tests.
5. Require no unbounded memory/thread/session growth.
6. Define acceptable transient-error/reconnect thresholds before running the test.

---

# 28. Definition of Done

The audit remediation program is complete when all of the following are true:

- [ ] Disconnect is exception-safe and idempotent.
- [ ] Temporary VISA settings are always restored.
- [ ] Public APIs expose consistent DPO-specific exceptions.
- [ ] Optional unsupported fields are distinguishable from transport failure.
- [ ] Hardcopy capture does not unnecessarily clear or permanently alter scope state.
- [ ] Settings restore validates payload format and instrument compatibility.
- [ ] Generic driver defaults are not tied to one physical scope serial number.
- [ ] Driver construction does not unexpectedly connect/write to disk.
- [ ] BUS/REF capability discovery is owned by public driver APIs.
- [ ] `get_all_bus_configurations()` never probes unavailable BUS slots when capability count is known.
- [ ] Editable values cannot inject additional SCPI commands.
- [ ] Default waveform transfer is deterministic binary acquisition.
- [ ] Duplicate channel labels cannot lose data.
- [ ] Multi-channel sample alignment is validated.
- [ ] GUI uses one persistent worker-owned VISA session while connected.
- [ ] Production GUI uses no nested `QEventLoop` for instrument operations.
- [ ] Application close during active I/O is safe.
- [ ] Full parameter refresh uses one instrument session.
- [ ] Final GUI no longer depends on the historical deep window inheritance chain.
- [ ] Architecture tests cover the complete production GUI dependency graph.
- [ ] Release dependency set is reproducible.
- [ ] Driver layer contains no interactive `input()` and avoids `print()` for normal operation.
- [ ] Python 3.10, 3.11, 3.12, and 3.13 CI passes.
- [ ] PySide6 offscreen CI passes.
- [ ] Required DPO4054 hardware regression tests pass.
- [ ] 24/72-hour soak qualification shows no unbounded resource growth.

## 29. Recommended execution order

Execute the work strictly in this order unless a failing test forces a prerequisite change:

1. lifecycle/cleanup and typed errors;
2. hardcopy/settings/default-state hardening;
3. capability API consolidation;
4. SCPI value safety;
5. waveform rewrite;
6. persistent worker session and asynchronous GUI actions;
7. GUI inheritance flattening;
8. release reproducibility and final documentation cleanup;
9. 24/72-hour hardware soak qualification.

Do not begin the GUI inheritance rewrite before the instrument session architecture and waveform API have stabilized. The GUI refactor should depend on final public application/driver interfaces rather than interfaces that are still being redesigned.
