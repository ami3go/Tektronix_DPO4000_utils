# A14 Advanced Trigger Backlog

Status: **A14.1, A14.2, A14.3, A14.4, A14.5 implemented** (`TriggerConfig` foundation, PULSE
width/runt/timeout, LOGIC pattern/setup-hold — see `dpo4000_utils/control.py`); A14.6-A14.9
planned, not implemented.
Parent docs: [`architecture.md`](architecture.md), [`regression-test-plan.md`](regression-test-plan.md)

This document is the authoritative scope/acceptance-criteria backlog for A14, the first
feature after the R0-F/R0-T baselines in the fixed development order in
`regression-test-plan.md`. It supplements that plan's regression levels, §14 timing
requirements, and §15 completion gate, which continue to govern how A14 is regression-tested.

## Current state

Trigger support today is edge-trigger-only:

- `dpo4000_utils/trigger.py` (`TriggerMixin`) and `control.py`'s `build_edge_trigger_commands()`
  / `configure_edge_trigger()` only ever write `TRIGGER:A:TYPE EDGE` plus
  `TRIGGER:A:EDGE:*`/`TRIGGER:A:LEVEL*`/`TRIGGER:A:MODE`.
- There is no `TriggerConfig` dataclass, unlike `ChannelConfig`/`AcquisitionConfig`/
  `DisplayConfig`. Edge trigger uses a bespoke keyword-arg builder instead
  (`build_edge_trigger_commands(*, source, slope, coupling, mode, level)`, `control.py:454`).
- `control.py:63` has an existing constant,
  `TRIGGER_TYPES = ("EDGE", "PULSE", "RUNT", "TIMEOUT", "LOGIC", "VIDEO")`, exported in
  `__all__` but referenced nowhere else in the repo. **It is factually wrong** — see
  Hardware findings below — and must be corrected as part of A14.1, not reused as-is.
- The Trigger tab GUI lives in the legacy widget stack (`gui_qt/main_window.py:375`
  `_build_trigger_tab()`), not yet extracted into `composition/pages/` the way
  `connection.py` was. It correctly uses only the public driver API today, but
  `main_window.py` is not in the AST-enforced `QT_BOUNDARY_FILES` list in
  `tests/test_gui_driver_boundary.py:23-40`, so that compliance isn't machine-checked.
- Test coverage is thin: SCPI-contract tests for edge trigger only
  (`tests/test_control.py:199-223`), one injection test (`tests/test_scpi_safety.py:129`),
  and trigger-state normalize/alias tests (`tests/test_acquisition_state.py:52-90`). No
  boundary/min-max tests for trigger level; no tests for `get_edge_trigger_configuration()`,
  `set_edge_trigger_source()`, `rearm_trigger_after_image()`, or `nudge_trigger_level_knob()`.

## Hardware findings (verified live against DPO4054, firmware v2.68, 2026-09-24)

Probed directly against `TCPIP0::192.168.0.5::INSTR` by writing each candidate value and
reading `*ESR?` (0 = accepted, 32 = command error) plus the readback query. State was fully
restored afterward (confirmed via a field-by-field `TRIGGER:A?` diff against the pre-probe
baseline).

**`TRIGGER:A:TYPE`** accepts exactly: `EDGE`, `LOGIC`, `PULSE`, `VIDEO`, `BUS`. Writing `RUNT`,
`TIMEOUT`, `TRANSITION`, `WINDOW`, or `SETHOLD` as a top-level type is rejected (`*ESR?` bit
for command error). **This means the existing `TRIGGER_TYPES` constant is wrong**: it includes
`RUNT`/`TIMEOUT` (which aren't top-level types) and omits `BUS` (which is).

**`TRIGGER:A:PULSE:CLASS`** (meaningful only when `TYPE=PULSE`) accepts: `WIDTH`, `RUNT`,
`TIMEOUT`, `TRANSITION`. Rejects `WINDOW`, `GLITCH`, `SETHOLD`. So on this firmware,
runt/timeout/transition triggers are **pulse-class sub-selections**, not independent trigger
types — A14.3 (Runt) and A14.5 (Timeout) below are implemented as `TRIGGER:A:TYPE PULSE` +
`TRIGGER:A:PULSE:CLASS {RUNT|TIMEOUT}`, not as separate `TYPE` values.

**`TRIGGER:A:LOGIC:CLASS`** (meaningful only when `TYPE=LOGIC`) accepts the literal value
`LOGIC` (the instrument's default/pattern-style class, echoed back abbreviated as `LOGI`) and
`SETHOLD`. `PATTERN`, `STATE`, and `TIMEOUT` as class names are rejected — those are not this
instrument's actual keywords for logic-class sub-selection, despite being common Tektronix
trigger terminology elsewhere.

Field layout for both classes is now mapped and implemented (`dpo4000_utils/control.py`):
for `LOGIC` (pattern) — `TRIGGER:A:LOGIC:FUNCTION {AND|OR|NAND|NOR}`,
`TRIGGER:A:LOGIC:INPUT:CH{1-4} {HIGH|LOW|X}` (`DONTCARE` is rejected; the literal token is
`X`), `TRIGGER:A:LOGIC:INPUT:CLOCK:SOURCE {CH1-4|NONE}`,
`TRIGGER:A:LOGIC:INPUT:CLOCK:EDGE {RISE|FALL}`, and — oddly namespaced differently from every
other `LOGIC` leaf — `TRIGGER:A:LOGIC:PATTERN:WHEN {TRUE|FALSE|LESSTHAN|MORETHAN}` (no
associated time-limit leaf could be found for the `LESSTHAN`/`MORETHAN` comparators, so those
values are accepted but any duration qualifier is unimplemented). `TRIGGER:A:LOGIC:THRESHOLD:
CH{1-4}` also exists (per-channel comparison level) but only the query side was verified; it
is not yet wired into `TriggerConfig`. For `SETHOLD` — `TRIGGER:A:LOGIC:SETHOLD:CLOCK:SOURCE
{CH1-4}`, `:CLOCK:EDGE {RISE|FALL}`, `:CLOCK:THRESHOLD <level>`, `:DATA:THRESHOLD <level>`,
`:SETTIME <time>`, `:HOLDTIME <time>` are all confirmed read+write. `:DATA:SOURCE` (which
channel is the data line) could not be found under any tried name and remains unmapped — a
`SETHOLD` config today can only threshold/time-qualify whatever the instrument's current data
source already is.

**`TRIGGER:A:VIDEO?`** returns a populated field set (`NTS;ALLL;1;0.0E+0;POS` — standard,
line spec, field, delay, polarity) confirming the video-trigger subsystem exists and is
queryable, but the individual sub-command names and full enum ranges are **not yet mapped**.

**`TRIGGER:B:TYPE?`** returns `EDG` successfully, confirming a full B-trigger (sequence)
subsystem exists in parallel to `TRIGGER:A:*`. Its event-count/mode structure is **not yet
mapped** — see the quirk below.

**`TRIGGER:A:HOLDOFF:VALUE?`** works and returns a time value in seconds (holdoff-by-time is
supported and readable at the byte level already exercised in `TRIGGER:A?`'s dump).

**Firmware quirk — bounded-timeout probing is mandatory, not optional**: two unsupported/
incorrectly-named queries (`TRIGGER:B:EVENTS:MODE?`, `TRIGGER:A:HOLDOFF:BY?`) did not return a
prompt SCPI error. They **timed out silently** (`VI_ERROR_TMO`) instead, requiring a full VISA
timeout to elapse before the caller got any response at all, and requiring a subsequent
`*CLS`/health check before continuing. Any A14 capability-probe code (see A14.10) must treat a
timeout the same as "not supported" and must never probe with the driver's normal/long
operational timeout — use a short, dedicated probe timeout so an unsupported command can't
stall a real capture/automation run. This directly informs the "unsupported-trigger capability
probe latency" requirement already named in `regression-test-plan.md` §14.

**Net implication for scoping below**: A14.1-A14.5 (type selection, pulse width, runt, logic,
timeout) are implemented with fully mapped fields, modulo the two explicitly-noted gaps above
(pulse `TRANSITION` class, `SETHOLD` data source, logic pattern `LESSTHAN`/`MORETHAN` time
qualifier). A14.6 (video), A14.7 (sequence/B-trigger), and A14.8 (holdoff-by-count, if it
exists) still need their full field layout mapped against real hardware or the Programmer
Manual before implementation starts on those specific sub-features — do not guess field names
for them.

## Feature matrix

| ID | Feature | SCPI foundation | Verification status | Priority |
|---|---|---|---|---|
| A14.1 | Trigger type selection & `TriggerConfig` dataclass | `TRIGGER:A:TYPE` | **Implemented** | Very high (blocks all others) |
| A14.2 | Pulse width trigger | `TRIGGER:A:TYPE PULSE`, `:PULSE:CLASS WIDTH` | **Implemented** | High |
| A14.3 | Runt trigger | `:PULSE:CLASS RUNT` | **Implemented** | High |
| A14.4 | Logic trigger | `TRIGGER:A:TYPE LOGIC`, `:LOGIC:CLASS` | **Implemented** (`LOGIC`/`SETHOLD` classes; `SETHOLD` data-source leaf and pattern time-qualifier unmapped) | Medium |
| A14.5 | Timeout trigger | `:PULSE:CLASS TIMEOUT` | **Implemented** | Medium |
| A14.6 | Video trigger | `TRIGGER:A:TYPE VIDEO` | Selector confirmed; field layout unmapped | Low |
| A14.7 | Sequence / B-trigger (A-then-B) | `TRIGGER:B:*` | Subsystem existence confirmed; event/mode structure unmapped | Medium |
| A14.8 | Trigger holdoff | `TRIGGER:A:HOLDOFF:VALUE` | Holdoff-by-time confirmed; holdoff-by-count/other modes unconfirmed | Medium |
| A14.9 | Trigger tab GUI integration + boundary enforcement | n/a (GUI/architecture) | n/a | High |
| A14.10 | HIL/regression qualification tie-in | n/a | n/a | Essential (gates completion) |

## Requirement details and acceptance criteria

### A14.1 — Trigger type selection & `TriggerConfig` dataclass

This is the foundation every other A14 sub-feature extends. Mirror the `ChannelConfig`
pattern (`control.py:138-150` dataclass; `control.py:70-89` fields/queries tuple+dict;
`control.py:293-335` command/query builders; `control.py:576-586` mixin methods) rather than
extending the existing bespoke `configure_edge_trigger(**kwargs)` signature.

Behavior:

- Replace the wrong `TRIGGER_TYPES` constant with the verified set
  `("EDGE", "LOGIC", "PULSE", "VIDEO", "BUS")`. `BUS` trigger overlaps with the existing
  `BusMixin` capability-gated serial-bus support (`dpo4000_utils/bus.py`) — A14 should reuse
  `get_available_bus_slots()`/licensing detection rather than re-implementing it, and should
  explicitly scope whether `TRIGGER:A:TYPE BUS` is in A14's initial delivery or deferred; it
  depends on already-capability-gated hardware the way decoded BUS transaction export does
  (`architecture.md:129`).
- New `TriggerConfig` dataclass (`frozen=True`, all fields `| None = None` except a required
  `trigger_type` or similar discriminator) with fields common to every type (source, slope
  where applicable, coupling, mode, level) plus nested/optional fields for type-specific
  parameters, following the existing `None`-means-"don't touch this field" convention.
- `build_trigger_config_commands(config)` / `build_trigger_config_queries()` mirroring
  `build_channel_config_commands`/`build_channel_config_queries`, going through the existing
  `normalize_*`/`format_scpi_number`/`normalize_scpi_enum` validators — this is also where
  SCPI-injection protection lives (mirror `tests/test_scpi_safety.py` coverage).
- `configure_trigger(config)` / `get_trigger_configuration()` mixin methods added to
  `TriggerMixin`, additive to (not replacing) the existing `configure_edge_trigger()` so
  existing callers/tests keep working; existing `configure_edge_trigger()` becomes a thin
  compatibility wrapper around `configure_trigger(TriggerConfig(trigger_type="EDGE", ...))`
  once the design is stable.
- Validate `trigger_type` against the confirmed real enum, not the old constant, before any
  I/O — mirror the existing structural-vs-capability-validation split in
  `regression-test-plan.md` §3.3.

Acceptance:

- Boundary/enum matrix (plan §3.1/3.2) for `trigger_type` and every new field: legal values
  accept, illegal/injected/malformed values reject with zero VISA writes.
- Exact-SCPI-contract tests (L1) for each accepted type's command sequence, mirroring
  `tests/test_control.py:199-223`'s style.
- `get_trigger_configuration()` round-trips a configured type back to normalized values
  without depending on `repr()` (plan §3.4).
- Existing edge-trigger tests/behavior (`configure_edge_trigger`, `set_trigger_level`,
  `get_trigger_level`, `get_edge_trigger_configuration`, `set_edge_trigger_source`,
  `rearm_trigger_after_image`, `nudge_trigger_level_knob`) remain unchanged per plan §15.1.

### A14.2 — Pulse width trigger — **Implemented**

`TRIGGER:A:TYPE PULSE` + `TRIGGER:A:PULSE:CLASS WIDTH`, `:PULSE:SOURCE {CH1-4|AUX|LINE}`,
`:WIDTH:POLARITY {POSITIVE|NEGATIVE}`, `:WIDTH:WHEN {LESSTHAN|MORETHAN|EQUAL|UNEQUAL|WITHIN|
OUTSIDE}`, `:WIDTH:LOWLIMIT`/`:WIDTH:HIGHLIMIT` (time). `TriggerConfig` fields:
`pulse_class="WIDTH"`, `pulse_polarity`, `pulse_when`, `pulse_low_limit`, `pulse_high_limit`.

Acceptance: L0-L1 boundary/injection/exact-contract tests in `tests/test_control.py` and
`tests/test_scpi_safety.py`; fake-VISA round-trip in `tests/test_trigger_config.py`; live
round-trip exercised by `hardware_verification_core.py`'s `trigger-config-write` case.

### A14.3 — Runt trigger — **Implemented**

`TRIGGER:A:PULSE:CLASS RUNT`, `:RUNT:POLARITY {POSITIVE|NEGATIVE|EITHER}`,
`:RUNT:WHEN {OCCURS|LESSTHAN|MORETHAN|EQUAL|UNEQUAL}`, `:RUNT:THRESHOLD:HIGH`/`:LOW`
(amplitude), `:RUNT:LOWLIMIT`/`:RUNT:HIGHLIMIT` (time). `TriggerConfig` fields:
`pulse_class="RUNT"`, `pulse_polarity`, `pulse_when`, `pulse_threshold_high`,
`pulse_threshold_low`, `pulse_low_limit`, `pulse_high_limit`.

Acceptance: same pattern as A14.2.

### A14.4 — Logic trigger — **Implemented** (LOGIC and SETHOLD classes)

`TRIGGER:A:TYPE LOGIC` + `TRIGGER:A:LOGIC:CLASS {LOGIC|SETHOLD}`. For `LOGIC` (pattern):
`:LOGIC:FUNCTION {AND|OR|NAND|NOR}`, `:LOGIC:INPUT:CH{1-4} {HIGH|LOW|X}`,
`:LOGIC:INPUT:CLOCK:SOURCE {CH1-4|NONE}`, `:LOGIC:INPUT:CLOCK:EDGE {RISE|FALL}`,
`:LOGIC:PATTERN:WHEN {TRUE|FALSE|LESSTHAN|MORETHAN}` (namespaced under `:PATTERN:` unlike
every other `LOGIC` leaf here — verified, not a typo). For `SETHOLD`:
`:LOGIC:SETHOLD:CLOCK:SOURCE {CH1-4}`, `:CLOCK:EDGE {RISE|FALL}`, `:CLOCK:THRESHOLD`,
`:DATA:THRESHOLD`, `:SETTIME`, `:HOLDTIME`. `TriggerConfig` fields: `logic_class`,
`logic_function`, `logic_input_ch1`..`logic_input_ch4`, `logic_clock_source` (shared leaf name,
different SCPI path per class), `logic_clock_edge`, `logic_when`, `logic_clock_threshold`,
`logic_data_threshold`, `logic_setup_time`, `logic_hold_time`.

Known gaps, not guessed around: `SETHOLD`'s data-source leaf (which channel is the "data"
line) could not be found under any tried name and is not settable; `LOGIC` pattern's
`LESSTHAN`/`MORETHAN` comparators accept no associated time-limit field (none found);
`TRIGGER:A:LOGIC:THRESHOLD:CH{1-4}` (per-channel pattern comparison level) is confirmed
readable but write behavior was never tested, so it is not wired into `TriggerConfig`.

Acceptance: explicit test that the pattern-vs-setup/hold class selector round-trips correctly
(`LOGI`/`SETH` abbreviations observed on this firmware) — see
`tests/test_trigger_config.py::test_get_trigger_configuration_logic_pattern_reads_class_specific_fields`
and the `_sethold_` equivalent.

### A14.5 — Timeout trigger — **Implemented**

`TRIGGER:A:PULSE:CLASS TIMEOUT`, `:TIMEOUT:POLARITY {STAYSHIGH|STAYSLOW|EITHER}`,
`:TIMEOUT:TIME` (duration). `TriggerConfig` fields: `pulse_class="TIMEOUT"`, `pulse_polarity`,
`pulse_timeout_time`.

Acceptance: same pattern as A14.2. Timeout-value boundary matrix includes the project's
standard non-finite/injection cases (plan §3.1) since this is a duration field.

### A14.6 — Video trigger

Behavior: `TRIGGER:A:TYPE VIDEO`, standard/line/field/polarity fields (`TRIGGER:A:VIDEO?`
confirmed queryable with populated fields; **individual leaf command names unmapped**).

Acceptance: same pattern as A14.2. Lowest priority — flag to the user whether this is worth
delivering in A14's first pass given DPO4054 use cases skew toward general-purpose bench work
rather than broadcast/video debug.

### A14.7 — Sequence / B-trigger (A-then-B)

Behavior: `TRIGGER:B:*` subsystem, parallel to `TRIGGER:A:*` (existence confirmed via
`TRIGGER:B:TYPE?` returning `EDG`). Event-count-before-B-arms and B-trigger type/level fields
are **unmapped**. The problematic `TRIGGER:B:EVENTS:MODE?` query from hardware probing
either uses a different command path than guessed or isn't supported on this firmware —
needs confirmation either way, not another blind retry with the driver's normal timeout.

Acceptance: same L0-L1 pattern as A14.1, plus this sub-feature specifically needs the bounded-
timeout capability probe from A14.10 built and working *first*, since even scoping this
correctly required discovering the timeout-instead-of-error behavior.

### A14.8 — Trigger holdoff

Behavior: `TRIGGER:A:HOLDOFF:VALUE` (confirmed working, returns seconds) for holdoff-by-time.
Whether a holdoff-by-event-count mode exists and its command path is **unconfirmed** — the
guessed `TRIGGER:A:HOLDOFF:BY?` query timed out rather than erroring, which is exactly the
ambiguous case A14.10's bounded-probe requirement exists for (can't distinguish "wrong command
name" from "unsupported but real command" without the manual).

Acceptance: holdoff-by-time boundary matrix (plan §3.1: near-zero, typical, maximum,
non-finite/injection). Do not add a by-count mode to `TriggerConfig` until its command path is
confirmed.

### A14.9 — Trigger tab GUI integration + boundary enforcement

Behavior: extend the existing Trigger tab (currently `gui_qt/main_window.py:375`
`_build_trigger_tab()`) to expose type selection and the newly-supported types' fields,
through `configure_trigger()`/`get_trigger_configuration()` only — never raw SCPI, per
`architecture.md`'s driver boundary rule.

Open question for the user (does not block A14.1-A14.8 starting): should A14.9 extend
`QT_BOUNDARY_FILES` in `tests/test_gui_driver_boundary.py:23-40` to cover `main_window.py`
as-is, or extract a dedicated `composition/pages/trigger.py` now (the way `connection.py`
was extracted, per `architecture.md:52-64`'s migration policy) so new trigger-type UI is
built composition-first rather than added to the legacy file? Either is consistent with the
migration policy; the second is more work but reduces future migration debt.

Acceptance: GUI contract snapshot (plan §3.5) — Qt object/property inspection of the extended
Trigger tab's controls/selector ranges/enabled-disabled relationships, mirroring
`tests/test_gui_qt_channel_config_metadata.py`'s style. New/extended boundary test proving no
raw SCPI or `.scope` access was introduced, mirroring
`tests/test_gui_driver_boundary.py:134-146`.

### A14.10 — HIL/regression qualification tie-in

Behavior: build the bounded-timeout capability-probe helper implied throughout this document
(short dedicated timeout, treats timeout as "unsupported," never blocks a real run) as a
reusable driver-level utility, not ad-hoc script code — this is load-bearing for A14.4/A14.6/
A14.7/A14.8's still-unmapped fields being probed safely later, and is explicitly named in
`regression-test-plan.md` §14 ("unsupported-trigger capability probe latency").

Acceptance, cross-referencing `regression-test-plan.md` §14's existing A14 list:

- trigger configuration latency and trigger readback latency baselined (extends
  `tests/baselines/r0_timing_baseline.json`'s operation set once A14 lands — a deliberate,
  reviewed baseline update per plan §16, not an automatic regeneration);
- Single arm → completion timing unaffected by new trigger types (reuse the existing
  `single_acquisition()`/`is_acquiring()` wait pattern already proven in
  `baseline_capture.py`/`hardware_verification_core.py`);
- timeout exactness for the new capability-probe helper itself;
- unsupported-trigger capability probe latency is bounded and does not expand the driver's
  normal VISA timeout (plan §14's explicit requirement, now grounded in the hardware
  quirk found above);
- applicable DPO4054 functional HIL (extend `tests/hardware/test_scope_api_hardware.py` and/or
  `scripts/run_hardware_verification.py`'s case set) and read-only/reversible/full profile
  coverage per `docs/hardware-verification.md`.

## Delivery phases

### Phase A — foundation (A14.1) — **done**

`TriggerConfig` dataclass, corrected type enum, `configure_trigger()`/
`get_trigger_configuration()`, full L0-L2 test coverage. Existing edge-trigger behavior
remains unchanged (regression invariant, plan §16).

### Phase B — confirmed-selector types (A14.2, A14.3, A14.5) — **done**

Pulse width, runt, timeout — all share the confirmed `TYPE PULSE` + `PULSE:CLASS` selector.
Field-level SCPI leaf names for each were verified and implemented.

### Phase B.5 — Logic trigger (A14.4) — **done**

Both `LOGIC` (pattern) and `SETHOLD` classes verified and implemented, with the `SETHOLD`
data-source leaf and the pattern `LESSTHAN`/`MORETHAN` time-qualifier left unmapped (see
A14.4's acceptance section) rather than guessed.

### Phase C — capability probing (A14.10)

Build the bounded-timeout probe helper before attempting the remaining unmapped types, so
A14.6/A14.7/A14.8 investigation itself doesn't repeat the hang this document's own research
run into.

### Phase D — remaining unmapped types (A14.6, A14.7, A14.8)

Video, sequence/B-trigger, holdoff-by-count (if it exists). Each requires its own
hardware/manual verification pass before implementation, per this document's "Hardware
findings" section.

### Phase E — GUI + qualification (A14.9, A14.10 completion)

Trigger tab integration, boundary enforcement decision, HIL qualification, baseline update.

## Definition of done

A14 is not complete until, per `regression-test-plan.md` §15's general gate applied here:

1. `TRIGGER_TYPES`/equivalent enum reflects only verified-real values (no repeat of today's
   wrong constant).
2. Every delivered sub-feature's SCPI leaf names are confirmed against real hardware or the
   Programmer Manual — none shipped on a guess.
3. Existing edge-trigger functional snapshots remain unchanged unless intentionally reviewed.
4. Boundary/enum/injection tests pass for every new field.
5. Exact SCPI/query contract tests pass for every delivered type.
6. GUI integration tests pass; boundary enforcement covers the extended Trigger tab.
7. The bounded-timeout capability-probe helper exists and is used for every not-yet-confirmed
   command path rather than assuming SCPI errors return promptly.
8. Applicable DPO4054 functional HIL passes for every delivered type.
9. R0-T timing baseline is explicitly, reviewably extended to cover new trigger operations.
10. Documentation (this file, `architecture.md`'s "Driver calls used" list, feature matrix)
    is updated to match what actually shipped.
