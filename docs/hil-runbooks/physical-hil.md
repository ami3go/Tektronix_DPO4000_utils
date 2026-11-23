# HIL-01 — Physical DPO4054 qualification: operator runbook

**State: TEMPLATE / NOT EXECUTED / NO HARDWARE PASS.** This document is an operator checklist, not an authorization or a record that the oscilloscope was accessed. See [global PR CI/closure](../ci-pr-closure-runbook.md) and [evidence form](physical-hil-evidence-template.md).

## 1. Scope and gating

Qualification targets a **real Tektronix DPO4054**, not a fake VISA session, simulator or an assumed IP/serial. Choose the *minimum* profile that supports the changed feature:

| Scope | Actual behavior | Permission | CI workflow |
|---|---|---|---|
| Strict read-only | Only approved single SCPI queries; preconfigured CURVE? with no DATA setup writes | Real bench owner authorizes read-only, exact serial/options and exclusive session | `hardware-api-tests.yml` with `profile=read-only` |
| Reversible | Trigger, DATA:*, channel, acquisition settings may be written and **must restore** | Separate explicit permission for reversible changes; exact approved *IDN? | `hardware-api-tests.yml` with `profile=reversible` |
| Full/disruptive | Acquisition/config changes + more invasive verification | Separate **full/disruptive** approval beyond reversible | `hardware-api-tests.yml` with `profile=full` |
| REF overwrite | A disposable REF memory slot is overwritten; setup restoration does **not** restore REF content | Independent approval specifying exact disposable REF1–REF4 | `profile=full`, `allow_reference_overwrite=true`, destination required |

**Stop / BLOCKED** if no operator, no exclusive bench, no actual verified serial/options, unavailable runner/connection, missing HIL permission, unsupported VISA exclusive lock, pre/post setup mismatch, unknown equipment state or unreviewed required SKIP. Do not enter sample values or change approvals to make a workflow start.

The GitHub self-hosted runner must have `self-hosted` and `dpo4000` labels. `hardware-api-tests.yml` shares `dpo4000-physical-bench` concurrency with `hardware-soak.yml`; A22/A25 workflows **do not yet share that lock** and require an independent bench schedule/exclusion check.

## 2. Operator preflight (complete BEFORE dispatch)

Record in [evidence template](physical-hil-evidence-template.md):
- PR number, approved candidate **full 40-hex SHA**, exact branch, requested profile and required public API/feature cases.
- Operator name/approval record, UTC start/end, reserved bench/host, same-scope identity via independent `*IDN?` and external label; serial and firmware. Explicit hardware options inventory, `NONE` when confirmed absent.
- True USB or TCPIP VISA resource and backend, runner OS + Python/PyVISA versions; do **not** use an example or the workflow's default as a verified resource.
- Probe Comp signal connected to CH1 only if the selected cases require it; observe high-impedance probe/input and documented fixture values. Missing waveform stimulus is SKIP, not PASS.
- A real pre-test setup fingerprint (e.g. `*LRN?`) and operator-approved restoration plan for any profile that writes. Confirm REF waveform storage is disposable before an overwrite.
- Close Desk, MCP, all other VISA clients and other self-hosted hardware jobs. Check no USB/TCPIP aliases are targeting the same reserved physical unit. Confirm safe recovery/emergency procedure.

**Hardware test admission is separate from software CI**, which must already be green on the tested head. No PIN, access key or other secret belongs in public PRs or logs.

## 3. GitHub Actions manual run (preferred)

Open [Hardware API Tests Actions](https://github.com/ami3go/Tektronix_DPO4000_utils/actions/workflows/hardware-api-tests.yml), choose **Run workflow**, and select the **exact approved candidate branch**. Check the checkout SHA in the job log, not just the branch name.

### Strict query-only inputs

- `visa_resource` — actual verified VISA resource; required, no fallback.
- `profile=read-only`.
- `authorized_bench=true` and `authorized_readonly=true` **only with operator approval**.
- `expected_serial` — independently verified exact serial.
- `verified_options` — confirmed inventory or `NONE`.
- `ch1_probe_comp_confirmed=true` only when actually connected.
- `test_channel=1`, `waveform_points=1000` (adapt only after reviewing scope configuration).
- `authorized_reversible=false`, `authorized_disruptive=false`, `allow_reference_overwrite=false`, `reference_destination=none`.

This path runs the hardware verifier and **only five reviewed query-only pytest modules** after verifier success: A15, A16, A20, A25 and the preconfigured waveform module. It must never be replaced by a blanket `pytest -m hardware tests/hardware` under strict read-only permission.

### Reversible/full inputs

For `profile=reversible`: additionally specify **full independently approved exact** `expected_idn` containing serial, set `authorized_reversible=true` and keep `authorized_disruptive=false`. For `profile=full` set `authorized_disruptive=true` only if separately approved. REF overwrite requires approved `reference_destination` (1–4) and `allow_reference_overwrite=true`. Confirm `authorized_bench=true` in every profile. A failed verifier prevents pytest follow-on.

### Equivalent local CLI (operator-run, actual bench ONLY)

Use only the profile independently authorized. Never execute these commands in ordinary CI or while Desk/MCP owns the scope.

```bash
# Manually set only after verified bench reservation and actual device identity:
export DPO4000_RESOURCE="<VERIFIED_REAL_VISA_RESOURCE>"
export DPO4000_EXPECT_SERIAL="<VERIFIED_EXACT_SERIAL>"
export DPO4000_VERIFIED_OPTIONS="<CONFIRMED_OPTIONS_OR_NONE>"
export DPO4000_EXACT_IDN="<FULL_VERIFIED_IDN_WITH_SERIAL>"
git rev-parse HEAD

# A: query-only; do not select or reconfigure a waveform source.
python scripts/run_hardware_verification.py \
  --resource "$DPO4000_RESOURCE" --profile read-only \
  --authorize-read-only --expected-serial "$DPO4000_EXPECT_SERIAL" \
  --verified-options "$DPO4000_VERIFIED_OPTIONS" \
  --test-channel 1 --waveform-points 1000 \
  --output-dir hardware_verification_reports/physical-hil-readonly

# B: reversible (ALTERNATIVE, not in addition to A; separately authorized).
python scripts/run_hardware_verification.py \
  --resource "$DPO4000_RESOURCE" --profile reversible \
  --expected-idn "$DPO4000_EXACT_IDN" --authorize-reversible-writes \
  --test-channel 1 --waveform-points 1000 \
  --output-dir hardware_verification_reports/physical-hil-reversible

# C: full (ALTERNATIVE; separately authorized, may change acquisition/setup).
# Requires the same exact --expected-idn and --authorize-reversible-writes,
# plus --authorize-disruptive-tests; REF overwrite needs separate flags.
```

Physical HIL commands are not dry-run examples: **running them contacts the scope**. The placeholder environment values will not identify a real instrument; the operator must replace and verify them. For automatic authorization and test selection, prefer the reviewed workflow, not arbitrary manual shell changes.

## 4. Required evidence and verdicts

Download the Actions artifact `dpo4000-hardware-verification-<run_number>` (retention normally 90 days). Record:

| Artifact / observation | PASS criterion |
|---|---|
| `verification_report.json`, `.md`, `.html` | Exact final SHA/resource/identity, actual case results and no unreviewed required failures |
| `pytest.xml` | Required selected hardware tests actually ran: zero failed/error; SKIPs listed individually and **never** credited as physical coverage |
| Device identity / option inventory | Model DPO4054, matching approved serial, actual VISA resource and backend, real acquisition/measurement readings |
| Pre/post setup snapshots | Strict read-only: identical setup hash, no setup writes; reversible/full: restoration `VERIFIED` or fail |
| Lock / transport / cleanup | Exclusive owner verified and scope released; no residual unsafe state after error/cancel |
| RAW data | Numeric result and context for each claimed test (units, scale, source, record length, timestamp); no synthetic values |
| GitHub provenance | PR SHA + run/job URLs, artifact hashes, operator approval and independent reviewer |

**Verdict:** `PASS` only for the specific executed, independently reviewed required cases. Use `FAIL` for observed mismatch, `BLOCKED` for missing/invalid permission or incomplete evidence, and `NOT_RUN` for unexecuted hardware. For PRs changing only docs, `NOT_APPLICABLE` can be justified without performing HIL. A passing verifier does **not** independently certify 24-hour soak, USB/TCPIP performance, A22 live, or full v0.9.0 release.

## 5. Recovery, upload and closure

If scope identity differs, any unexpected write occurs, setup restoration fails or the scope becomes unresponsive: **stop subsequent tests**, preserve logs/setup snapshots, notify the operator for controlled recovery; never automatically retry invasive commands. Attach artifacts or SHA-256 hashes plus actual Actions URLs to the PR and fill [physical HIL evidence form](physical-hil-evidence-template.md). If required proof is missing, leave the PR hardware gate BLOCKED.

**Related:** [strict read-only qualification](../dpo4054-readonly-hil.md), [hardware verification](../hardware-verification.md), [A22 test matrix](../a22-test-matrix.md), [A25 test matrix](../a25-test-matrix.md).
