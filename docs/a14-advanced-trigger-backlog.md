# A14 Advanced Trigger Backlog

Status: **software implementation complete through A14.9; A14.10 qualification harness implemented, live DPO4054 qualification and measured R0-T baseline update pending**.

Parent docs: [`architecture.md`](architecture.md), [`regression-test-plan.md`](regression-test-plan.md)

This document is the authoritative scope and qualification record for A14. It records both what is implemented and what still requires real-hardware evidence. A14 must not be called fully qualified until the live HIL and measured timing-baseline gates at the end of this document pass.

## Current implementation

A14 now has three layers:

1. **Driver/configuration API**
   - `TriggerConfig` and `configure_trigger()` / `get_trigger_configuration()` cover the verified A-trigger families.
   - `SequenceTriggerConfig` and `configure_sequence_trigger()` / `get_sequence_trigger_configuration()` cover B-trigger/sequence operation.
   - `AdvancedTriggerMixin` adds verified holdoff-by-time and bounded SCPI capability probing.
2. **Production GUI**
   - `dpo4000_utils/gui_qt/composition/pages/trigger.py` owns the composition-first Advanced Trigger page.
   - The page uses public driver methods only and follows the asynchronous `_run_action(..., on_success=...)` contract.
3. **Qualification**
   - deterministic L0/L1/L2 tests cover validation, SCPI contracts, timeout recovery, and GUI boundary behavior;
   - opt-in DPO4054 HIL covers holdoff and the known unsupported/hanging B-trigger probe;
   - `HardwareBaselineCapture` now measures A14 trigger apply/readback and unsupported-probe latency for the next explicit R0-T capture.

No undocumented trigger command is exposed merely because a likely spelling exists. Unmapped features stay unavailable until verified against hardware or the Programmer Manual.

## Verified hardware findings

The trigger command research below was performed live against a DPO4054 running firmware v2.68 on 2026-09-24. Candidate writes were checked with `*ESR?`, read back where possible, and the original setup was restored after probing.

### A-trigger type selector

`TRIGGER:A:TYPE` accepts:

- `EDGE`
- `LOGIC`
- `PULSE`
- `VIDEO`
- `BUS`

`RUNT`, `TIMEOUT`, `TRANSITION`, `WINDOW`, and `SETHOLD` are not top-level trigger types on this firmware. The corrected `TRIGGER_TYPES` model therefore reflects the real selector rather than treating pulse/logic subclasses as independent types.

`BUS` is a real top-level selector, but its full A14 trigger-configuration subtree has not been mapped end-to-end, so the A14 GUI does not expose BUS trigger configuration.

### Pulse trigger

`TRIGGER:A:PULSE:CLASS` accepts:

- `WIDTH`
- `RUNT`
- `TIMEOUT`
- `TRANSITION`

The delivered A14 surface implements WIDTH, RUNT, and TIMEOUT. TRANSITION remains deliberately hidden because its full field layout was not mapped and qualified.

Verified delivered leaves include:

- source;
- WIDTH polarity, comparator, low limit, high limit;
- RUNT polarity, comparator, low/high time limits, high/low thresholds;
- TIMEOUT polarity and timeout duration.

### Logic trigger

`TRIGGER:A:LOGIC:CLASS` accepts `LOGIC` and `SETHOLD`.

Delivered LOGIC/pattern fields include:

- function `AND|OR|NAND|NOR`;
- CH1-CH4 input states `HIGH|LOW|X`;
- clock source `CH1-CH4|NONE`;
- clock edge `RISE|FALL`;
- pattern condition `TRUE|FALSE|LESSTHAN|MORETHAN`.

Delivered SETHOLD fields include:

- clock source `CH1-CH4`;
- clock edge;
- clock threshold;
- data threshold;
- setup time;
- hold time.

The SETHOLD data-source leaf and a duration qualifier for pattern `LESSTHAN`/`MORETHAN` remain unmapped and are not guessed.

### Video trigger

Verified/delivered fields include:

- source `CH1-CH4`;
- standard `NTSC|PAL|SECAM`;
- line;
- field `ALLLINES`;
- polarity `POSITIVE|NEGATIVE`.

A fourth positional field visible in the aggregate `TRIGGER:A:VIDEO?` response could not be mapped to a verified leaf and remains unimplemented.

### Sequence / B-trigger

B-trigger is a separate layer over A-trigger and therefore uses `SequenceTriggerConfig` instead of a `TriggerConfig.trigger_type` value.

Verified/delivered leaves include:

- `TRIGGER:B:STATE`;
- B edge source, slope, coupling, level;
- `TRIGGER:B:BY {TIME|EVENTS}`;
- `TRIGGER:B:TIME`;
- `TRIGGER:B:EVENTS:COUNT`.

**Live constraint:** enabling B-trigger is rejected unless A-trigger is already EDGE. The GUI documents this, and HIL ordering restores/configures A=EDGE before enabling B.

### Holdoff

`TRIGGER:A:HOLDOFF:VALUE` / `TRIGGER:A:HOLDOFF:VALUE?` is verified as holdoff-by-time in seconds and is now exposed through:

- `set_trigger_holdoff()`;
- `get_trigger_holdoff()`;
- optional `holdoff=` on `configure_trigger()`;
- `holdoff` in `get_trigger_configuration()`.

Holdoff input is validated before any I/O. Negative, non-finite, malformed, or injected values are rejected with zero VISA writes.

A holdoff-by-count/event API is **not** exposed. `TRIGGER:A:HOLDOFF:BY?` is known to time out silently on this firmware, and no verified count-mode leaf has been found. A future count implementation requires a separate hardware/manual verification pass.

### Firmware timeout quirk

The DPO4054 does not always return a prompt SCPI error for unsupported queries. At least these candidates were observed to time out silently:

- `TRIGGER:B:EVENTS:MODE?`
- `TRIGGER:A:HOLDOFF:BY?`

Therefore exploratory capability detection must never inherit the normal operational VISA timeout.

`AdvancedTriggerMixin.probe_scpi_query()` implements the required policy:

1. validate a single argument-free query before I/O;
2. temporarily cap the active VISA timeout (default 500 ms);
3. clear stale status before probing;
4. treat a timeout as unsupported rather than as evidence that the whole session is dead;
5. recover with `*CLS` and a bounded `*IDN?` health check;
6. for prompt responses, sample `*ESR?` so a command error is still reported as unsupported;
7. restore the exact previous VISA timeout on every exit path;
8. never expand an already-shorter active timeout.

Non-timeout transport failures remain real transport failures and are not disguised as unsupported capabilities.

## Feature matrix

| ID | Feature | Foundation | Current status |
|---|---|---|---|
| A14.1 | Trigger type selection and `TriggerConfig` | `TRIGGER:A:TYPE` | **Implemented and tested** |
| A14.2 | Pulse width | `TYPE PULSE`, `PULSE:CLASS WIDTH` | **Implemented and tested** |
| A14.3 | Runt | `PULSE:CLASS RUNT` | **Implemented and tested** |
| A14.4 | Logic / setup-hold | `TYPE LOGIC`, `LOGIC:CLASS` | **Implemented for verified fields; unmapped leaves intentionally omitted** |
| A14.5 | Timeout | `PULSE:CLASS TIMEOUT` | **Implemented and tested** |
| A14.6 | Video | `TYPE VIDEO` | **Implemented for verified fields; unmapped fourth aggregate field omitted** |
| A14.7 | Sequence / B-trigger | `TRIGGER:B:*` | **Implemented and tested; A must be EDGE to enable B** |
| A14.8 | Trigger holdoff | `TRIGGER:A:HOLDOFF:VALUE` | **Holdoff-by-time implemented; unverified count mode intentionally not exposed** |
| A14.9 | Trigger GUI integration | composition Trigger page | **Implemented with GUI contract + boundary tests** |
| A14.10 | HIL/regression qualification | bounded probe + HIL + R0-T capture | **Harness implemented; live HIL and measured baseline evidence pending** |

## Delivered API behavior

### A-trigger configuration

`TriggerConfig` follows the existing configuration-object pattern: optional fields mean "do not touch this field", and structural validation occurs before VISA I/O. Existing edge-trigger convenience methods remain compatible.

The supported A14 GUI surface is intentionally narrower than the raw `TRIGGER:A:TYPE` enum:

- EDGE;
- PULSE: WIDTH, RUNT, TIMEOUT;
- LOGIC: LOGIC, SETHOLD;
- VIDEO.

BUS and PULSE/TRANSITION stay hidden until their field-level configuration paths are qualified.

### Holdoff-by-time

`configure_trigger(config, holdoff=...)` validates the holdoff before applying the trigger config. This preserves the zero-I/O-on-invalid-input contract: an invalid holdoff cannot leave a partially applied trigger configuration.

`set_trigger_holdoff(value, verify=True)` writes the verified leaf and optionally reads it back. `get_trigger_configuration()` includes the holdoff readback.

### B-trigger

B-trigger is configured independently from A-trigger. TIME enables the delay-duration field; EVENTS enables the event-count field. GUI controls mirror that relationship.

## GUI integration decision

A14.9 chose the composition-first route rather than adding more behavior to the legacy Trigger page.

`composition/pages/trigger.py` provides:

- A-trigger type selection;
- type-specific stacked controls;
- trigger mode;
- optional holdoff-by-time;
- sequence/B-trigger controls;
- readback projection;
- dynamic enable/disable relationships for pulse, logic, and B-delay modes.

The production compatibility surface routes `_build_trigger_tab()` to this composed page. Existing acquisition, trigger-level, horizontal-position, and image-rearm controls are retained where the mature host exposes them.

The page calls only public driver methods. It does not access `.scope`, call raw `.query()`/`.write()`, or configure VISA directly. Readback updates use asynchronous `on_success` continuations instead of consuming `_run_action()` synchronously.

## Deterministic test coverage

A14-specific tests now include:

- exact holdoff command/query contracts;
- finite/non-negative/injection validation;
- zero I/O when holdoff or capability-query input is invalid;
- exact EDGE + holdoff command sequence;
- holdoff set/readback;
- advanced trigger readback including holdoff;
- capability-probe validation;
- temporary timeout capping and exact restoration;
- proof that a requested probe timeout never expands an already shorter timeout;
- prompt SCPI error (`*ESR? != 0`) handling;
- raw timeout and project `DPOTimeoutError` recovery paths;
- GUI composition routing;
- GUI public-driver boundary enforcement;
- A-trigger type/class widget contract;
- pulse/logic/B-trigger enabled-state relationships;
- asynchronous GUI dispatch contract.

The public hardware-verification manifest also classifies and exercises the newly added methods, so adding A14 APIs cannot silently bypass the repository's public-API HIL coverage guard.

## HIL qualification

`tests/hardware/test_a14_advanced_trigger_hardware.py` adds opt-in tests for:

- known-good `TRIGGER:A:HOLDOFF:VALUE?` capability probe;
- known unsupported/hanging `TRIGGER:B:EVENTS:MODE?` bounded probe and recovery;
- restoration of the normal VISA timeout;
- reversible holdoff write/readback when write tests are enabled.

The normal public hardware verifier also exercises holdoff/probe readbacks and reversible holdoff write/readback according to its profile.

These tests must run against the DPO4054 self-hosted hardware runner before A14 is marked fully qualified.

## R0-T timing qualification

`HardwareBaselineCapture.capture_timing()` now emits these A14 timing operations in addition to the existing baseline set:

- `trigger_config_apply` — repeated configure of a verified PULSE/WIDTH configuration;
- `trigger_config_readback` — repeated `get_trigger_configuration()`;
- `unsupported_trigger_probe` — repeated bounded `TRIGGER:B:EVENTS:MODE?` capability probes.

The trigger benchmark snapshots the scope setup, establishes the verified PULSE/WIDTH condition, measures apply/readback separately, and restores the original setup in `finally` before later acquisition timing runs.

The unsupported-probe benchmark records the configured dedicated probe timeout, requires every candidate to remain unsupported/recovered, and asserts that the operational VISA timeout is unchanged after every sample.

The existing `single_acquisition` timing remains the regression measurement for arm-to-completion behavior after A14.

**Important:** `tests/baselines/r0_timing_baseline.json` is not auto-edited with invented numbers. The three new operation values must be captured on the DPO4054, reviewed, and then committed explicitly. Thresholds for the new operations must likewise be chosen from measured evidence rather than copied blindly from unrelated operations.

The capture and live-comparison CLIs expose `--capability-probe-timeout-ms` (default 500 ms) so the A14 probe benchmark itself cannot inherit the normal long timeout.

## Deferred / intentionally unimplemented areas

These are not A14 regressions; they remain outside the delivered verified surface until separately researched:

- A-trigger BUS field-level configuration;
- PULSE/TRANSITION field layout;
- SETHOLD data-source leaf;
- LOGIC pattern duration qualifier for LESSTHAN/MORETHAN;
- VIDEO aggregate fourth-field leaf;
- holdoff-by-count/event mode.

Any future research into these paths must use `probe_scpi_query()` or an equivalent bounded mechanism. Direct exploratory queries with the normal operational timeout are prohibited by this A14 qualification policy.

## Completion gate

A14 software delivery is complete only if normal CI remains green. Full A14 qualification additionally requires all of the following:

1. verified-real trigger enums/leaf names only;
2. no guessed SCPI field exposed publicly;
3. existing edge-trigger behavior remains compatible;
4. boundary/enum/injection tests pass;
5. exact SCPI/query contracts pass;
6. GUI integration and driver-boundary tests pass;
7. bounded capability-probe behavior and timeout restoration tests pass;
8. applicable DPO4054 HIL passes on the self-hosted hardware runner;
9. a fresh measured R0-T baseline is captured and reviewed with `trigger_config_apply`, `trigger_config_readback`, and `unsupported_trigger_probe` values;
10. architecture and A14 documentation match the shipped surface.

At the state represented by this branch, items 1-7 and 10 are implemented in code/tests/docs. Items 8-9 remain evidence gates and must not be marked complete without a live hardware run.
