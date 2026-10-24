# DPO4054 strict read-only HIL qualification

**Task:** DPO4054-READONLY-HIL-01. **Release result without physical hardware:** BLOCKED.

This qualification is based on the P0 verifier from PR #53. Software qualification is not
evidence of a successful physical DPO4054 run. The bench owner must supply a real VISA
resource, exact verified serial, authorization, exclusive ownership and a working VISA backend.
No default VISA address is a valid substitute for identifying the instrument.

## Admission gates

1. Confirm bench availability, operator permission, exclusive ownership and safe probe
   connections. CH1 Probe Comp is required only for stimulus-dependent checks; absent
   stimulus is a **SKIP**, not a pass.
2. Obtain the intended resource from VISA discovery on the bench PC. Independently
   verify `*IDN?` (manufacturer, DPO4054 model, serial and firmware) with the operator.
   Record installed options using confirmed device documentation; do not blindly issue
   unsupported queries under this authorization.
3. Ensure a single instrument owner. The verifier requests a VISA exclusive lock;
   an unsupported or unsuccessful lock fails closed. The Actions job also serializes
   runs under the `dpo4000-exclusive-bench` concurrency group.
4. Verify the baseline setup is saved before qualification and compared to the final
   `*LRN?` setup string. A mismatch fails. No setup restoration is issued in strict
   mode because restoration itself is a configuration write.
5. Never run the entire `tests/hardware/` directory with a read-only authorization.
   Hardware tests are not automatically safe merely because write tests are disabled.

## Strict query-only verifier

```bash
python scripts/run_hardware_verification.py \
  --resource "$DPO4000_RESOURCE" \
  --profile read-only \
  --authorize-read-only \
  --expected-serial "$DPO4000_EXPECT_SERIAL" \
  --verified-options "$DPO4000_VERIFIED_OPTIONS" \
  --test-channel 1 --waveform-points 1000 \
  --output-dir hardware_verification_reports/readonly
```

The verifier wraps the active VISA session in a fail-closed query-only adapter.
Configuration writes, `*CLS`, raw/binary write operations, compound SCPI commands and
VISA device clear are rejected before instrument I/O. The adapter records query and
blocked-operation counts, which appear in JSON evidence. The fixture also verifies the
instrument model, exact serial and setup equality. VISA exclusive-lock and close failures
must be treated as **FAIL**, never ignored.

An additional strictly limited `read_preconfigured_waveform()` API uses only
`DATA:SOURCE?`, `DATA:START?`, `DATA:STOP?`, outgoing preamble queries
and `CURVE?`. It cannot select CH1 or shorten a record, so an unsuited current
transfer configuration is a **SKIP** with a reason. The operator must preconfigure
the source/encoding/window before the no-write campaign; the test harness does
not reconfigure the scope. Long records require a separately raised bounded
transfer ceiling. The CH1 tests require confirmation of Probe Comp wiring.

The preexisting public waveform reader is **not query-only**. It changes
`DATA:SOURCE`, `DATA:START`, `DATA:STOP`, `DATA:WIDTH` and `DATA:ENCDG`.
The existing PNG hardcopy changes `SAVE:IMAGE:FILEFORMAT` and invokes
`HARDCOPY START`. Both are **SKIP** under strict no-write authorization.
The A14 capability probe transmits `*CLS`, so it is also excluded.
A second authorization to allow reversible configuration changes would be
a different profile and does not qualify as this campaign.

## Reviewed focused test selection

`.github/workflows/hardware-api-tests.yml` uses these modules for read-only dispatch:

| Module | Covered feature | Restrictions |
| --- | --- | --- |
| `test_a15_recipe_hardware.py` | A15 query-only recipe | Write test is skipped; read-only timing is allowed |
| `test_a16_rule_hardware.py` | A16 acquired holdoff value | True comparison against scope values |
| `test_a20_measurement_trend_hardware.py` | A20 measured trend samples | SKIP if no active, finite MEAS |
| `test_a25_headless_job_hardware.py` | A25 read-only recipe/report | Uses independently opened short-lived session |
| `test_dpo4054_readonly_waveform_hardware.py` | CH1 CURVE?, scaling, A18 DPOE, A21 NPZ/DPOZ | Requires operator-confirmed Probe Comp and a preconfigured outgoing transfer within the cap |

The complete hardware suite is **not** invoked for read-only dispatch, since other
modules use `*CLS`, unsupported-command probes or transfer configuration writes.

## Coverage and evidence interpretation

| Coverage | Strict read-only status |
| --- | --- |
| Connection / session / identity / CH1–4 labels | Executable after bench admission |
| Analog, MATH, REF, BUS and MEAS1–8 setup readbacks | Executable; optional hardware SKIP must be explicit |
| Basic/advanced trigger, B-trigger holdoff | Query readback only; known timeout probes excluded |
| Acquisition state / completion | Query readback only; no RUN/STOP/force trigger |
| Setup snapshot and final comparison | Executable, initial/final `*LRN?` must match |
| Waveform raw samples / scaling / long records | Query-only `CURVE?` path can exercise the already-configured source/window and scale; must SKIP if window exceeds authorized ceiling or setup is unsupported |
| PNG screenshot | BLOCKED pending independently proven query-only device method |
| A15, A16, A20, A25 | Selected read-only pytest modules; PASS only after bench execution |
| A18 waveform evidence, A21 NPZ/DPOZ from real traces | Selected query-only preconfigured waveform pytest can produce both artifacts; physical PASS pending |
| Fault injection (timeout/disconnect/cancel etc.) | Offline mocks first; no deliberate live transaction interruption |

Artifacts must include exact tested Git SHA, device serial/firmware/options if verified,
VISA resource/backend, case PASS/FAIL/SKIP reasons, data values, baseline/final setup,
JSON/Markdown report, JUnit XML and Actions run/artifact URLs. A missing capability,
unexecuted case, or no physical bench must never be recorded as hardware PASS.

## Authorized self-hosted workflow

Run the manual **Hardware API Tests** workflow on the dedicated
`[self-hosted, dpo4000]` runner. Select `read-only`, supply the actual VISA resource
and serial plus the independently verified installed-option inventory (or `NONE`),
and set `authorized_readonly=true`. All write authorization inputs remain
false. An operator must separately certify the bench wiring, VISA backend, scope options,
physical ownership and probe-comp connection before dispatch.

No workflow was dispatched as part of software-only preparation; the hardware gate
remains **BLOCKED** until qualified on the intended physical DPO4054.
