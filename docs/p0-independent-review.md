# Independent technical audit — P0 DPO4054 release gates (PR #53)

**Task:** DPO4000-P0-INDEPENDENT-REVIEW-01  
**Review date:** 2026-10-24  
**PR:** https://github.com/ami3go/Tektronix_DPO4000_utils/pull/53  
**Branch:** `feat/p0-dpo4054-qualification-release-gates`  
**Initial reviewed revision:** `3bf3d54491f5fd7ae6f61dd6167c9f6f2f2ea466`  
**Disposition:** **DRAFT / RELEASE BLOCKED**. This is an automated technical review, **not** approval by an independent qualified human functional-safety reviewer.

## Reviewed software and upstream behavior

The review inspected the P0 baseline capture/comparison, 24/72-hour soak runner,
soak evidence validator, offline P0 release evaluator, hardware verifier,
unit tests, both manual hardware workflows and the P0 qualification runbook.

Upstream APIs examined include `dpo4000_utils/hardware_verification_core.py`,
`hardware_verification.py`, `baseline_capture.py`, `baseline_compare.py`,
`settings.py`, `waveform.py`, `hardcopy.py` and physical pytest cases in
`tests/hardware/`.

In particular, `read_waveform()` sends `DATA:SOURCE`, `DATA:START`,
`DATA:STOP`, `DATA:WIDTH` and `DATA:ENCDG` writes before reading `CURVE?`.
Hardcopy sends `SAVE:IMAGE:FILEFORMAT` and `HARDCOPY START`.
The *names* of these public APIs are not proof they are read-only.

## Confirmed findings and corrections

| ID | Severity | Component | Root cause and concrete reproducer | Correction / regression |
|---|---|---|---|---|
| IR-01 | **CRITICAL** | `.github/workflows/hardware-api-tests.yml` | Selecting a write-capable profile without authorization failed the preflight, but `pytest -m hardware` had `if: always()`. `DPO4000_ENABLE_WRITE_TESTS` was still derived from the profile, potentially executing state-changing physical cases after rejection. | Run pytest only after successful verifier/preflight; `test_rejected_hardware_preflight_cannot_fall_through_to_pytest`. |
| IR-02 | **HIGH** | `hardware_verification_core.py`, `tests/hardware/*` | The public waveform/hardcopy methods were declared READ_ONLY despite physical SCPI writes. A default read-only hardware workflow would exercise them; the hardware status test unconditionally sent `*CLS`. | Reclassified as REVERSIBLE; gated affected hardware pytest cases on explicitly approved `DPO4000_ENABLE_WRITE_TESTS`; risk-manifest regression. |
| IR-03 | **HIGH** | `hardware_verification_core.py` | `_restore_baseline()` stored a post-restore snapshot but returned success even when `*LRN?` readback differed from the original. | Require identical setup and identity readback or fail; `test_verifier_requires_exact_scope_setup_restore_readback`. REF waveform *contents* remain non-restorable. |
| IR-04 | **HIGH** | `validate_soak_report.py` | A single successful cycle plus claimed `elapsed_s=86400` and `status=PASS` could be accepted without 8,640 scheduled cycles being accounted for. | Require scheduled-cycle/deadline accounting, beginning and end samples, bounded gaps, wall/monotonic duration agreement; adversarial one-cycle/wall-clock tests. |
| IR-05 | **HIGH** | `evaluate_p0_release.py` | R0 `comparison_report.json` status was trusted, without recomputing functional and p95 regressions from raw R0 evidence. A fabricated PASS with absent raw timing coverage could satisfy P0-G2. | Recompute raw differences using the upstream comparison APIs; reject missing p95, absent coverage, identity/transport/commit mismatches, missing reviewed thresholds; forge-PASS regression. |
| IR-06 | **HIGH** | `evaluate_p0_release.py` | A reported low p95 could contradict retained raw duration samples, while synthetic or incomplete capture omitted waveforms. | Verify finite `samples_s`, count, min/p50/p95/max, timeout/error counts, restore verification, capture configuration and required waveform sizes; `test_reported_p95_cannot_contradict_raw_monotonic_samples`. |
| IR-07 | **HIGH** | `evaluate_p0_release.py`, `validate_soak_report.py` | Duplicate JSON keys silently replaced earlier failing fields; symlinked artifacts or traversal could redirect trusted file paths. An evidence file could also change between hash and parse. | Reject duplicates/symlinks/traversal; hash the same bytes evaluated; exercise adversarial JSON and symlink tests. |
| IR-08 | **HIGH** | `evaluate_p0_release.py` | Required HIL `SKIP` could count as PASS if the claimant marked `capability_absent`, allowing missing qualification to pass. | Required feature cases must PASS; capability-based scope exclusions need independently reviewed policy change; SKIP regression. |
| IR-09 | **HIGH** | `evaluate_p0_release.py` | Software CI claims accepted any nonempty URL, without checking per-job exact candidate SHA or action-run provenance. JUnit suite counts without testcases could be credited. | Require exact-head commit for each job and repository action URL, nonempty testcases, zero skipped/failed/error cases; forged CI/empty JUnit regressions. |
| IR-10 | **HIGH** | `.github/workflows/hardware-soak.yml` | Unauthorized dispatch skipped the entire job, which could leave a green workflow without a performed soak. USB/TCPIP aliases were not serialized across both physical workflows. | Failed mandatory authorization step and shared `dpo4000-physical-bench` concurrency; static workflow regressions. |
| IR-11 | **HIGH** | `scripts/run_hardware_soak.py` | A failed `scope.connect()` could strand its partially initialized VISA handle. Tiny unbounded intervals could retain millions of measurements during long runs. | Disconnect on connection failure; require interval >=5 s, with monotonic deadline validation retained. |
| IR-12 | **HIGH** | `scripts/capture_r0_baseline.py`, `scripts/compare_r0_baseline.py` | Unsafe live capture could modify setup without positive restoration evidence or correct IDN. | Reuse existing `VerifiedSetupGuard` for preflight, backup, post-restore confirmation and recorded evidence. No second redundant restore. |
| IR-13 | **HIGH** | `hardware-api-tests.yml` | REF slot 4 was implicitly selected by workflow dispatch, permitting accidental destructive memory overwrite if `allow_reference_overwrite` was set. | Default destination `none`; require a separate explicit disposable REF slot and full/disruptive authorization. |
| IR-14 | **HIGH** | `evaluate_p0_release.py` | An apparent software-only PASS could omit independent USB/TCPIP cross-transport review, extra performance metrics or a threshold approval. | Required cross-transport rollup, immutable artifact hashes, reviewed threshold SHA and nonempty extra performance observations (concurrent hardening to PR #53). |
| IR-15 | **HIGH** | `hardware_verification_core.py`, `run_hardware_verification.py`, hardware API workflow | Invasive qualification could accept a generic vendor substring without binding the reserved physical scope's model and serial before SCPI writes. Selecting another attached instrument could modify an unapproved bench setup. | Require a complete exact approved DPO4054 `*IDN?` for reversible/full runs, compare before any invasive case, and require explicit bench authorization even for read-only workflow dispatch. Offline test confirms no VISA construction without a valid target. |

**Severity** describes initial failure potential. A correction being committed does not itself
certify that it is fully verified: **exact-final-head CI and independent human assessment
are still required**, and additional findings could emerge.

## Risk-workstream conclusions

### R1. Instrument write authorization

READ_ONLY, REVERSIBLE and DISRUPTIVE classes must follow actual emitted SCPI
commands, not method names. Destructive REF waveform overwrite requires a separately
authorized full profile *and* an explicit disposable REF destination. A write-capable runner must bind the complete exact approved DPO4054
model/serial identity before proceeding with any invasive case. Setup backup and
verified post-restore readback are mandatory before accepting write-capable HIL evidence.
Configuration restoration does not recover destructively overwritten REF waveform memory.
Hardware workflows must not run pytest after authorization failures.

### R2. Immutable performance baselines

An approved R0 baseline is never implicitly overwritten. Candidate and baseline paths
and identity/transport must remain separate. Candidate files must match exact candidate
source SHA. Each timing operation must retain actual distribution samples, finite
statistics, zero failed samples and approved thresholds. Unknown, unmeasured or
unthresholded operations do not qualify. Neither a reporter's PASS flag nor a
synthetic approval record is independent evidence.

### R3. Long-duration soak

An interrupted, incomplete, failed-postflight or under-covered run must never
claim PASS. Monotonic elapsed time, independent wall-clock consistency,
bounded scheduling drift, actual scheduled cycle count, identity/setup stability,
fatal exceptions, cleanup failures, resource-growth limits and restored connection
health are release-significant. A retained JSON/Markdown file cannot by itself
prove a scope was physically operating for 24 hours; authorized on-bench
provenance review remains mandatory.

### R4. Offline release gate

The evaluator must not create VISA or SCPI sessions. It rejects missing evidence,
malformed JSON, nonfinite numbers, duplicate keys, symlinks/traversal,
mismatched source SHA, missing HIL feature cases, forged comparison statuses,
invalid raw timing statistics and missing human approval metadata. Hashes
provide **integrity checking only**, not proof that hardware evidence was
captured honestly. Human signoff must be verified directly in GitHub and
against actual bench records.

### R5. Workflows and execution

Hardware runs remain manual `workflow_dispatch`, pinned to designated
`self-hosted, dpo4000` runners, with separate authorization and shared
physical-bench concurrency. Keep artifact upload after failure; do not allow
false green skipped authorization. Workflow secrets, runner network access,
VISA device access and GitHub permissions must be reviewed by the bench owner.

## Software test evidence and limits

Regression module: `tests/test_p0_independent_review.py`, alongside
`tests/test_p0_qualification_guards.py` and existing hardware/session suites.
Adversarial fixtures include forged 24-hour elapsed durations, incomplete
scheduled coverage, malformed/duplicate JSON keys, symlink evidence,
false CI PASS, HIL SKIP, falsified raw performance p95, missing JUnit
testcases, unapproved review, and a monkeypatched VISA resource manager
that would raise if the offline evaluator tried to connect.

**Do not report full CI PASS until the exact latest PR head's GitHub Actions
runs are completed and independently inspected** for Python 3.10/3.11/3.12/3.13,
Ruff, full pytest, PySide6, CodeQL and Linux/Windows package builds.
Local hardware is not attached to this software review, and hosted CI is
not a substitute for DPO4054 HIL.

## Still-blocked release requirements

1. Final-head completed software/GUI/security/packaging CI and triage of any failing jobs.
2. Independently authorized DPO4054 read-only, reversible, disruptive and disposable-REF
   bench qualification with verified setup restoration.
3. Separate real USB and TCPIP baselines, candidates, approved thresholds,
   full raw timing coverage and independently approved transport rollup.
4. One physically witnessed uninterrupted >=24-hour DPO4054 soak with actual
   scheduled samples and postflight health.
5. A25 installed headless CLI hardware/second-session qualification,
   traceable retained evidence and physical runner isolation review.
6. Formal approval from an **independent qualified human** reviewer, not this
   automated report. PR #53 remains DRAFT and cannot be merged or released.

## Review evidence handling

The release manifest's `artifacts_sha256` binds the bytes consumed, but the
reviewer must separately retrieve, verify, and approve evidence from trusted
GitHub Actions and physical bench sources. Offline `review.json` is not a
signature. Do not populate human-review approval fields on behalf of the reviewer.
