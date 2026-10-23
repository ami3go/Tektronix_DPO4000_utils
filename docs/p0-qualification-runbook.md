# DPO4054 v0.9.0 P0 qualification / release gate handoff

Task: `DPO4000-P0-QUALIFICATION-RELEASE-01`  
Status as of 2026-10-23: **BLOCKED / NOT QUALIFIED**. This document is a
procedure and audit trail, not a physical-HIL pass certificate.

## Baseline and change isolation

- Starting `main`: `8a5b6cfcf794104a3f428799bd415874a8392d72`.
- `pyproject.toml`: `0.9.0rc1`; supported Python `>=3.10`.
- A25 code hardening stays in draft PR #50, `feat/a25-headless-job-runner`.
- A22 streaming stays in draft PR #51 and must **not** be merged as part of this gate.
- README feature matrix stays in PR #52.
- Cross-cutting qualification hardening is draft PR #53,
  `feat/p0-dpo4054-qualification-release-gates`.
- Never present earlier software success as evidence from the current candidate SHA.

### Gate matrix

| Gate | Requirement | Result at handoff | Remaining evidence |
| --- | --- | --- | --- |
| P0-G0 | Current combined software, GUI, Ruff, security and packages | PENDING | Exact-head CI matrix and reviewer evaluation |
| P0-G1 | Full DPO4054 read-only/reversible/authorized full HIL | BLOCKED | Physical VISA/IDN/setup + feature evidence |
| P0-G2 | USB and TCPIP R0-F/R0-T baseline and comparison | BLOCKED | Separately measured raw per-transport distributions, reviewed gates |
| P0-G3 | One continuous >=24 h DPO4054 soak | BLOCKED | Complete final JSON/Markdown artifacts and independent review |
| P0-G4 | A25 software, packaged CLI, independent review, HIL, integration | BLOCKED | PR #50 final-head release/QA/HIL and controlled merge |

**Critical:** an authorized physical DPO4054, exclusive VISA ownership, stable
Probe Comp fixture and a reserved Windows or Linux bench are required. No
hosted mock/virtual test substitutes for this evidence.

## Identified P0 software weaknesses and corrections in PR #53

1. **HIGH: Baseline capture could overwrite a previously approved snapshot.**
   Snapshot publication now refuses existing files and creates an exclusive
   complete file; existing approved snapshots are never silently rewritten.
2. **HIGH: Comparison could ignore missing operations, unsupported coverage,
   missing thresholds and mismatched transport/instrument ID.** Comparison
   now fails closed and records coverage gaps; acceptance thresholds must be
   independently reviewed rather than guessed or widened.
3. **CRITICAL: Soak could report PASS even when it ended nearly a full
   interval early, and did not enforce postflight identity/recovery.**
   Exact monotonic duration, final live readback, initial/final identity,
   configuration-drift checks and cleanup failures are now gating.
4. **HIGH: Soak evidence was not durable at intermediate progress or
   atomically finalized.** Add checkpointed, atomic JSON/Markdown;
   interrupted, failed, running and passed states are distinct.
5. **HIGH: Soak did not guard same-resource concurrent runs and lacked
   thread/latency acceptance evidence.** Add resource-specific host lock,
   peak RSS/Python/FD/thread gates, latency distribution/drift and retained
   acceptance limits. Stale lock removal requires bench-owner verification.
6. **CRITICAL: Reversible/disruptive verifier and R0 entry points lacked
   sufficiently explicit run-time authorization checks.** Require explicit
   CLI approval and separate workflow inputs. No default disposable REF
   target is selected for an overwrite request.

These are code-review findings and remediations, not an independent external
review signoff. Review the final diff and CI outputs separately.

## Operator preflight (both transports, individually)

1. Reserve the physical scope and test PC. Disable automatic sleep, reboot
   and scheduled maintenance. Verify storage capacity.
2. Connect CH1 probe tip and ground to front-panel Probe Comp as described
   in `docs/regression-testing.md`; verify a suitable signal.
3. Verify the real `*IDN?` and record manufacturer, DPO4054 model, serial,
   firmware, installed options, the exact VISA resource and actual VISA
   backend. Never infer addresses from examples.
4. Record the current setup before any write-capable case and retain a
   verified restore snapshot. Obtain separate reversible/full/REF approvals.
5. Confirm no other VISA client owns the instrument.
6. Use the **exact tested commit SHA** with installed dependencies.

Commands shown below deliberately use an operator-supplied
`DPO4000_RESOURCE`; do not substitute an unverified address.

```bash
python -m pip install -c constraints-release.txt -e '.[dev,pyside6]'
python -m ruff check .
QT_QPA_PLATFORM=offscreen python -m pytest -q tests
python scripts/run_regression_batch.py --all-tests
```

Record every CI run URL, exit code, test count and skipped/failure reason
separately for Python 3.10, 3.11, 3.12 and 3.13; collect CodeQL and
Windows/Linux packaging outcomes. Hosted CI completion alone does **not**
open the hardware gate.

## P0-01 — physical API / feature qualification

Read-only smoke; write no configuration:

```bash
python scripts/run_hardware_verification.py \
  --resource "$DPO4000_RESOURCE" --profile read-only \
  --test-channel 1 --waveform-points 1000 \
  --output-dir qualification_reports/hardware/usb/read-only
DPO4000_HARDWARE=1 DPO4000_RESOURCE="$DPO4000_RESOURCE" \
  python -m pytest -q -m hardware tests/hardware
```

Set the output path to `hardware/tcpip/` when using Ethernet. Invoke the
manual `.github/workflows/hardware-api-tests.yml` with verified resource,
IDN and `profile=read-only`; the runner labels are
`[self-hosted, dpo4000]`. The workflow's default resource is illustrative
only; verify it first.

Only following explicit **reversible** bench approval:

```bash
python scripts/run_hardware_verification.py \
  --resource "$DPO4000_RESOURCE" --profile reversible \
  --authorize-reversible-writes --test-channel 1 \
  --waveform-points 1000 \
  --output-dir qualification_reports/hardware/usb/reversible
```

For full/disruptive cases, require **both**
`--authorize-reversible-writes` and `--authorize-disruptive-tests`.
REF memory overwrite additionally requires `--allow-reference-overwrite`
and an **explicit**, approved `--reference-destination 1..4`.
Stop all later invasive cases if final setup readback differs from snapshot.
Retain `verification_report.json`, `verification_report.md`, HTML,
setup snapshots and all hardware JUnit results. Mark unsupported options
SKIP/UNSUPPORTED with reasons rather than claiming PASS.

## P0-02 — transport-separated R0 measurements

**WARNING: Both canonical R0 scripts issue physical setup writes.**
Execute only with reversible authorization. Do not capture or compare in
read-only instrument-owner conditions.

On known-good approved baseline checkout, separately for USB and TCPIP:

```bash
python scripts/capture_r0_baseline.py \
  --resource "$DPO4000_RESOURCE" \
  --output-dir qualification_reports/performance/usb/baseline \
  --authorize-reversible-writes \
  --reps-standard 20 --reps-heavy 5 --reps-waveform-large 5
```

Store the USB and Ethernet captures under separate, immutable directories.
Review and explicitly approve candidate thresholds. Do not auto-approve or
overwrite a reference when testing a suspected regression. Then on the
candidate checkout, **against the matching transport and physical unit**:

```bash
python scripts/compare_r0_baseline.py \
  --baseline-dir qualification_reports/performance/usb/baseline \
  --thresholds tests/baselines/r0_timing_thresholds.json \
  --resource "$DPO4000_RESOURCE" \
  --authorize-reversible-writes \
  --output-dir qualification_reports/performance/usb/candidate
```

Repeat with `performance/tcpip/` and its own VISA resource. Never compare
USB against TCPIP. The comparison now refuses completion if its threshold
file omits measured operations or the capture explicitly labels some
operations `not_yet_covered`. This is intentional: expand real coverage,
measure it, then propose explicitly reviewed limits. Required additional
A15/A18/A21/A25 timing, GUI heartbeat, cancellation and resource growth
must be measured; do not synthesize them.

## P0-03 — continuous 24-hour read-only soak

Run only after G0 and read-only G1 smoke pass, on an exclusively reserved
scope/host. No automatically scheduled hosted CI starts this run.

```bash
python scripts/run_hardware_soak.py \
  --resource "$DPO4000_RESOURCE" --duration-hours 24 \
  --interval-seconds 10 \
  --output-dir qualification_reports/soak/dpo4054-24h

python scripts/validate_soak_report.py \
  --report-dir qualification_reports/soak/dpo4054-24h \
  --min-hours 24 --expected-commit "$(git rev-parse HEAD)"
```

Alternatively dispatch `.github/workflows/hardware-soak.yml` on the
approved self-hosted runner, with `authorized_bench=true`,
`duration_hours=24` and explicit VISA resource. It runs offline
structural validation and uploads retained artifacts even if the run fails.

A checkpoint with `status=RUNNING`, an interrupted run, a short run,
a failed final VISA query, missing evidence or a cleanup error **cannot**
qualify. The validator's structural success does not by itself prove real
hardware execution; retain trusted runner logs and complete provenance.

## P0-04 — A25 final physical and packaging gate

Complete draft PR #50's hosted matrix and Windows/Linux package jobs.
Dispatch its `.github/workflows/a25-headless-hil.yml` on branch
`feat/a25-headless-job-runner` with exact `visa_resource` and
`expected_idn`, using a real, exclusively owned DPO4054. The workflow
runs installed `dpo4000-job` with a read-only A15 holdoff recipe, A16 rule,
JSON report validation and a second connection to prove session release.
Retain `a25-evidence/hardware-cli-report.json`,
`a25-evidence/hardware-junit.xml`, software JUnit and installed CLI
benchmark. Explicitly review report exit code, actual measurement, identity
and cleanup. Reversible A25 cases require fresh approval.

## Final release decision

Before merging/publishing stable v0.9.0, inspect retained outputs from the
**final, combined candidate commit**, ensure all four gates passed, preserve
setup restoration evidence and obtain independent qualified engineering
review. Never infer a hardware PASS from an offline unit test, released
package, PR description or successful action without an actual scope.


## Offline final release manifest

After all independently captured artifacts have been deposited under the
same exact-commit `qualification_reports/` root, run:

```bash
python scripts/evaluate_p0_release.py \
  --root qualification_reports \
  --expected-commit "$(git rev-parse HEAD)"
```

This deterministic, **offline/no-VISA** validator writes
`qualification_reports/manifest.json`, `summary.json`, and `summary.md`
with per-gate PASS/FAIL/BLOCKED, evidence SHA-256 digests and a nonzero exit
for incomplete qualification. Missing evidence is **BLOCKED**, not PASS.
The input manifest contract requires:

- `software/ci.json`: schema version 1, exact commit, each Python 3.10–3.13,
  Ruff, PySide6, CodeQL, and Windows/Linux packaging job PASS plus run URLs.
- `hardware/qualification.json`: schema version 1, exact commit, actual
  DPO4054 IDN, independently verified setup restoration and a `cases` array
  mapping each required feature family to its measured supporting artifact.
  A hardware SKIP must have capability-absent evidence and an explicit reason.
- `performance/{usb,tcpip}/baseline/r0_{functional,timing}_baseline.json`:
  immutable, separately approved real-device R0 references. Each candidate
  folder has a `comparison_report.json` and raw
  `r0_candidate_{functional,timing}.json` with matching SHA-256.
- `soak/soak_report.{json,md}`: one uninterrupted continuous 24-hour
  physical run, validated with the separate soak validator.
- `a25/qualification.json`, `hardware-cli-report.json` and
  `hardware-junit.xml`: installed CLI and second-session evidence from
  the dedicated authorized workflow, plus independent review status.
- `review.json`: exact combined candidate commit, named reviewer,
  `status=APPROVED`, `critical_open=0`, `high_open=0`.

This tool validates **integrity, structure, gate completeness and traceability**.
It cannot independently attest that a scope, measurement, signature or approval
is authentic. Human bench evidence review and independent engineering signoff
are mandatory. Do not fabricate these input files to obtain a PASS.
