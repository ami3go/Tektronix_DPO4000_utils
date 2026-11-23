# DPO4000-CI-GLOBAL-001 — CI execution, evidence, and PR closure runbook

**Applies to:** every pull request targeting `main` in `ami3go/Tektronix_DPO4000_utils`, including code, documentation, dependencies, packaging, CI workflows, MCP, and qualification work.
**Scope:** software PR **merge approval**, PR **closure without merge**, hardware qualification, and stable-release approval are **different decisions**. This runbook is a procedure, not evidence that a test ran.
**Maintainers:** review applicability at every PR head; update this inventory whenever a workflow or required gate changes. Start from the PR checklist in `.github/PULL_REQUEST_TEMPLATE.md`, then publish the final closure record in `docs/pr-closure-evidence-template.md`.

## 1. Non-negotiable evidence rules

1. Identify the **final 40-character head commit SHA** (`git rev-parse HEAD`) and PR base/merge commit. Do not combine results from previous heads, different PRs or a baseline commit. When GitHub tests a synthetic PR merge commit, inspect `head_sha`, `merge_commit_sha` and what SHA the workflow checked out; record both, and rerun if the tested merge is stale.
2. Classify every relevant check as **PASS**, **FAIL**, **PENDING**, **BLOCKED**, or **NOT_APPLICABLE**, with reason and independent reviewer. A missing, cancelled, timed-out, neutral, skipped, queued or in-progress **required** check is *not PASS*. A path-filtered workflow may be NOT_APPLICABLE only after a documented change-scope review.
3. Retain **workflow/job URL, run ID, exact revision, conclusion, test counts, failure/skip reasons, JUnit XML and artifacts** wherever available. A screenshot, PR statement, synthetic benchmark or handcrafted JSON is not independently verified provenance.
4. A pull request may be **merged** only after all *applicable* required CI checks are green, review findings are addressed, and any applicable hardware/qualification gate has separately been satisfied. If a gate cannot run, record **BLOCKED**, not a fabricated PASS or an unchecked waiver.
5. A PR may be **closed without merge** for supersession/abandonment. Record the reason and replacement PR/commit; never mark its changes delivered or treat tests as qualification.
6. Physical VISA/HIL requires explicit bench-owner authorization and exclusive resource ownership. **Never auto-dispatch HIL on PR pushes or in hosted CI.** Reject operation until the runner, scope identity, serial, options, probe fixture and intended permission profile are independently verified.
7. **No raw hardware operations are authorized by this runbook.** Instructions below are for an approved operator on the dedicated bench. No CI runner, AI agent or maintainer should infer approval from text or the existence of a workflow.
8. Changes to accepted thresholds, security permissions, mandatory gate definitions, HIL safety classification or release manifests require an explicit separately reviewed rationale; do not relax a check to make a PR green.

## 2. Change-class decision matrix

Every PR must identify one or more classes; apply the **union** of their checks. `CORE` is always required when the workflow runs for the PR, and is the default for every PR targeting `main`.

| Class | Required software CI and focused evidence | Additional acceptance |
|---|---|---|
| **DOC** Docs / template only | CORE, link/command review, runbook-inventory contract; Pages deploy **after merge** if path triggers | No HIL unless the docs change is itself a qualification claim |
| **DEP** Dependencies / Python / packaging | CORE, pinned-environment resolution, Windows/Linux build and startup/integrity checks | Explain compatibility/version and licensing/security changes; HIL only if instrument behavior is affected |
| **DRV** SCPI/transport/driver/control/waveform | CORE, driver regression + fault/timeouts/restore/SCPI boundary tests | Applicable read-only or reversible **physical** verification for behavior-qualifying changes; exact USB/TCPIP cases when claimed |
| **GUI** Qt/worker/Desk | CORE, offscreen PySide6, worker/session concurrency, package startup | Physical validation if hardware behavior/real-time responsiveness changes |
| **A22** Live streaming | CORE, `a22-hosted-temp` when changed paths match + `tests/test_a22_*.py`, synthetic benchmark | Authorized A22 HIL **both USB and TCPIP** for hardware/FPS/skew/restoration claims; required record sizes, no silent 1M SKIP |
| **A15/A16/A18/A20/A21** Recipes/rules/evidence/scientific/trend | CORE, focused feature tests + fail-closed/schema/atomicity checks, relevant synthetic benchmarks | Relevant physical A15/A16/A20/trace evidence only when qualifying physical behavior |
| **A25** Headless CLI | CORE, A25 CLI validation/exit-code/cancellation tests and benchmark | Manually authorized A25 HIL for claims about actual DPO4054 operation and second-session cleanup |
| **AUT/LOG** Automation/logger | CORE, focused automation/logger tests, stress/backpressure/reconnect/artifact tests | Authorized Probe Comp HIL for physical operation claims, with setup restoration evidence |
| **MCP** Agent protocol | CORE, MCP SDK/client contract, auth and ownership, mock-VISA/fault tests on supported Python/OS matrix | MCP offline workflow from PR #80 (not on `main` yet); **no physical claim** before cross-process Desk ownership and separately authorized HIL |
| **CI/SEC** Workflow, permission, auth, safety controls | CORE, CodeQL, independent review of workflow expression/permissions, static policy and negative tests | No untrusted code on physical bench; manual HIL workflow gate reviewed without dispatch |
| **REL** Stable release/P0 qualification | ALL applicable hosted jobs, real USB+TCPIP R0 evidence, hardware API qualification, >=24h soak, A25, final manifest | Independent qualified human reviewer and approved same-candidate SHA; **no stable release with BLOCKED gates** |

**DOC does not mean "ignore failed required CI".** An unrelated infrastructure failure needs documented cause and a repeatable green result or independent branch-policy resolution. Do not silently remove branch protections.

## 3. Verified workflow inventory on `main` (2026-11-23)

The following paths, triggers, jobs and evidence are taken from the repository workflow files. **Only `Tests`, `CodeQL`, and `DPO4054 Strict Read-Only Offline Safety` are unconditional hosted pull-request checks**. Build and A22 hosted workflows have path filters. Physical workflows need manual dispatch.

| Workflow | Trigger | Target / required results | Evidence |
|---|---|---|---|
| `.github/workflows/tests.yml` | PR to main; push main | Ruff; core Python 3.10, 3.11, 3.12, 3.13 on Linux; 3.12 Windows; offscreen PySide6; offline R0 regression + A18/A20/A21/A25/A22 benchmarks; A25 validate-only CLI | Actions run/job conclusions, `ci-evidence/` benchmark artifact, A22 synthetic JSON, A25 validated report in logs |
| `.github/workflows/codeql.yml` | PR to main; push main; Monday schedule | CodeQL Python `security-extended` complete, no newly unreviewed alert | Job URL, category, security alert adjudication |
| `.github/workflows/read-only-offline-tests.yml` | PR to main; selected branch push | Strict read-only guard, preconfigured waveform, P0 qualification-guard unit tests; Ruff | `dpo4054-strict-readonly-offline` artifact (`readonly_offline_junit.xml`) |
| `.github/workflows/build-gui-executables.yml` | PR with selected paths; main release-note path; tags; manual | Windows ZIP + packaged startup; Linux binary, DEB, AppImage, Flatpak startup; integrity checks/SBOM/SHA256 | `DPO4000Desk-windows`, `DPO4000Desk-linux-packages`, `DPO4000Desk-integrity`; inspect `Release integrity` job |
| `.github/workflows/a22-hosted-temp.yml` | PR with A22-specific paths | `pytest -q -s tests/test_a22_*.py`; synthetic 1k, 10k, 100k, 1M array performance | `a22-hosted-synthetic-benchmark` JSON (not physical FPS) |
| `.github/workflows/hardware-api-tests.yml` | **manual** | [self-hosted,dpo4000] verifier and profile-selected HIL tests; separate read-only/reversible/full authorization | `dpo4000-hardware-verification-<run_number>` containing verification reports/JUnit |
| `.github/workflows/a22-hil-qualification.yml` | **manual** | [self-hosted,dpo4000] A22 real transfer, setup snapshot/restore; approved reversible DATA writes | `a22-dpo4054-real-hardware-<run_id>` JSON |
| `.github/workflows/a25-headless-hil.yml` | **manual** | [self-hosted,dpo4000] installed A25 CLI read-only recipe, rule report, setup-before/after equality | `a25-read-only-hil-<run_id>` directory |
| `.github/workflows/hardware-soak.yml` | **manual** | [self-hosted,dpo4000] authorized 24/72-hour real soak and independent validator | `dpo4000-soak-<duration>h-<run_number>` with complete reports |
| `.github/workflows/pages.yml` | **push** main with docs/README/workflow paths; manual | Publish static docs after merge; **not a pre-merge PR check** | Deployment URL and successful job on merged main SHA |

**Pending addition:** PR [#80](https://github.com/ami3go/Tektronix_DPO4000_utils/pull/80) adds `.github/workflows/mcp-offline.yml` (PR-triggered, Linux/Windows × Python 3.11/3.13, SDK in-process checks and CLI smoke). Apply this gate to #80 and future MCP PRs once available; until merged it is **not** an existing `main` workflow.

**Important workflow limitation:** `hardware-api-tests.yml` and `hardware-soak.yml` share `dpo4000-physical-bench` concurrency. **A22 HIL and A25 HIL do not currently declare this shared concurrency group**; A25 HIL also has no explicit authorization input. They must be manually bench-reserved, and a separate safety-hardening PR should unify physical bench locking/authorization. This runbook must not imply the YAML already enforces global exclusion. These workflows must not be started while any other VISA client or hardware workflow controls the instrument.

## 4. Exact-revision local CI mirror (NO physical I/O)

Use a fresh checkout of the PR, capture the 40-digit revision and Python environment. Do **not** set `DPO4000_HARDWARE=1`, provide a physical resource, or execute `tests/hardware` in this stage.

```bash
git fetch origin
git checkout <FINAL_PR_HEAD_40_HEX_SHA>
git status --short
git rev-parse HEAD
python --version
python -m pip install -e '.[dev,pyside6]'
python -m ruff check dpo4000_utils tests scripts tektronix_utils.py
QT_QPA_PLATFORM=offscreen python -m pytest -q
python scripts/run_regression_batch.py --hardware skip --all-tests --summary ci-evidence/r0-regression.json
python scripts/benchmark_a22_live_stream.py --sizes 1000,10000,100000,1000000 --iterations 5 --output ci-evidence/a22-synthetic-benchmark.json
dpo4000-job --recipe tests/data/a15_recipe_minimal.json --validate-only --report ci-evidence/a25-validate-report.json
```

`git checkout` must target an existing verified SHA; `<FINAL_PR_HEAD_40_HEX_SHA>` is a required operator value. Create `ci-evidence/` before running output-producing commands (`mkdir -p ci-evidence`). On Windows, run equivalent commands in PowerShell; `QT_QPA_PLATFORM=offscreen` is a per-process environment variable, not a Windows command.

For a clean Python 3.10 job, install `.[dev]` rather than extras which no longer support that interpreter. For the complete compatibility matrix repeat on supported interpreters and **trust the hosted job results only after checking the same final head**.

For specific classes, run these additionally:

```bash
# A22
python -m pytest -q tests/test_a22_*.py

# A25 (no VISA resource)
python -m pytest -q tests/test_a25_*.py
dpo4000-job --help

# Strict read-only safety regression
python -m pytest -q tests/test_read_only_guard.py tests/test_read_only_waveform.py tests/test_hardware_verification.py tests/test_p0_qualification_guards.py

# MCP (only on a checkout containing PR #80; Python >=3.11)
python -m pip install -e '.[dev,mcp]'
python -m pytest -q tests/test_mcp_gateway.py tests/test_mcp_protocol.py
dpo4000-mcp --help
```

Shell globs such as `tests/test_a22_*.py` expand on POSIX shells; for Windows use explicit filenames or `python -m pytest -q tests -k a22`. Do not present synthetic `a22`, `a25` or MCP fake-VISA performance data as physical throughput. Read `.github/workflows/tests.yml` and `.github/workflows/build-gui-executables.yml` for exact CI packaging commands; package-smoke and checksum jobs cannot be replaced by local unit tests.

**Minimum software PASS:** clean exit code, no failed/error tests, no unexpected skips, all relevant Actions jobs on the latest SHA completed successfully, reproducible regression metrics, documented known warnings, retained artifacts and reviewed change scope.

## 5. Read-only GitHub Actions evidence collection

Use read-only GitHub CLI commands after the workflows complete. Do **not** re-run or dispatch workflows as part of a review without the appropriate authorization.

```bash
gh pr view <PR_NUMBER> --repo ami3go/Tektronix_DPO4000_utils --json headRefOid,baseRefName,mergeable,reviewDecision
gh pr checks <PR_NUMBER> --repo ami3go/Tektronix_DPO4000_utils
gh run list --repo ami3go/Tektronix_DPO4000_utils --commit <FINAL_HEAD_SHA> --limit 100
gh run view <RUN_ID> --repo ami3go/Tektronix_DPO4000_utils --json headSha,status,conclusion,workflowName,jobs
gh run download <RUN_ID> --repo ami3go/Tektronix_DPO4000_utils --dir ci-evidence/downloads
```

GitHub run records can be for the synthetic PR merge revision: record both PR head and actual checkout SHA. Record every applicable job, including queued/failed/skipped status; **do not count a previous successful workflow run from an older commit**. Verify that the downloaded artifact corresponds to the recorded run ID and compare file SHA-256 as appropriate. A green `gh pr checks` alone does not satisfy an untriggered required feature-specific or HIL gate.

## 6. Physical HIL gate selection and exact results

**Only after** a bench owner authorizes the operation, reserves the physical scope, verifies precise VISA resource, DPO4054 model + serial + firmware, installed options, probe wiring, VISA runtime, tested commit and no competing Desk/MCP client. Store operator approval in the closure record; never put secrets/PINs into public logs. Workflow UI: repository **Actions → select workflow → Run workflow**, select the exact authorized branch and validate its SHA. The self-hosted runner must have labels `self-hosted` and `dpo4000`.

### H1 — Strict query-only hardware API

Run `hardware-api-tests.yml` with `profile=read-only`, real `visa_resource`, `authorized_bench=true`, `authorized_readonly=true`, exact `expected_serial`, `verified_options` (or `NONE`), and `ch1_probe_comp_confirmed=true` only when actually connected. Keep reversible/disruptive/REF-overwrite flags **false**. The workflow runs the verifier then its *reviewed read-only subset* of physical pytest tests. Do not use an unrestricted `pytest -m hardware tests/hardware` under read-only authorization.

Equivalent bench CLI **only when authorized**:

```bash
python scripts/run_hardware_verification.py \
  --resource "$DPO4000_RESOURCE" --profile read-only \
  --authorize-read-only --expected-serial "$DPO4000_EXPECT_SERIAL" \
  --verified-options "$DPO4000_VERIFIED_OPTIONS" \
  --test-channel 1 --waveform-points 1000 \
  --output-dir hardware_verification_reports/readonly
```

**Accept only:** verifier exit 0; exact identity/serial/options; scoped query-only count and zero unapproved writes; mandatory cases PASS; JUnit pass/fail/skip with reasons; baseline and final setup equal; clean lock/session release; complete `verification_report.{json,md,html}` and retained action artifact. A skipped unsupported feature is **not qualified**, and a required release case cannot be converted to PASS.

### H2 — Reversible/full hardware API

`hardware-api-tests.yml` with `profile=reversible` requires `authorized_bench=true`, exact approved `expected_idn`, `authorized_reversible=true` and explicit resource. `profile=full` additionally requires `authorized_disruptive=true`; REF overwrite requires a separately approved disposable destination. Before/after setup restoration and exact identity are mandatory. **Do not dispatch** based on an earlier approval or a generic TEKTRONIX identity.

**Accept only:** complete case coverage, reversible mutations within approved limits, verified restored `*LRN?`, no hidden failures, full JSON/HTML/Markdown + JUnit + artifact hashes. A structural PR that does not change live behavior need not run H2; record NOT_APPLICABLE with review rationale.

### H3 — A22 live scope qualification

`a22-hil-qualification.yml` requires `reversible_writes_authorized=YES`, `exclusive_instrument_confirmed=YES` and `restore_approved=YES` plus real `visa_resource`, independently checked `expected_idn`, appropriate `run_seconds`, `point_sizes` and `target_hz`. Repeat on **USB and TCPIP separately** for cross-transport claims. Standard point sizes are 1k/10k/100k/1M; operator must preconfigure sufficient horizontal record length. For CH1–CH4 coverage, inspect `tests/hardware/test_a22_live_stream_hardware.py` and explicitly set the approved `DPO4000_A22_MULTI_CHANNELS=YES` environment where required; the YAML by itself does not expose that as a dispatch input.

**Accept only:** measured actual sample count, transfer duration, achieved rate (not requested Hz), complete four-channel group, skew, error/timeout count, memory-growth and setup restoration. If 1M is SKIP due to short scope record length, **do not certify full 1M coverage**; rerun after approved setup change. See `docs/a22-test-matrix.md`.

### H4 — A25 real CLI qualification

`a25-headless-hil.yml` requires independently recorded bench-owner approval, exclusive booking and verified `visa_resource` / `expected_idn`; the workflow **currently has no authorization checkbox**, so workflow dispatch alone is not approval. It prepares a read-only holdoff recipe, runs `dpo4000-job --validate-only`, a real installed CLI call and the scoped API hardware test.

**Accept only:** `a25-evidence/validation.json` with validation-only + exit 0; `hardware-cli-report.json` with schema/version, status=pass, exit_code=0, completed recipe and A16 PASS; `hardware-junit.xml`; matching `setup-before.json`/`setup-after.json` identity and SHA-256; separate sessions fully released; raw job URL and artifact. See `docs/a25-test-matrix.md`.

### H5 — Automation/logger real operation

There is no dedicated hosted Automation/Logger Actions dispatch in the verified `main` workflow inventory. Use operator-run `scripts/run_automation_logger_hil.py` on the exclusively reserved bench, **only with approved reversible setup changes**; use `--help` for options and verified resource. The runner temporarily configures scope, so this is **not strict read-only**. See `docs/automation-logger-hil.md`.

**Accept only:** `hil_report.{json,md}`, `hil_run.log`, `environment.json`, raw PNG/CSV/DPO4LOG and profiles, tracebacks on failure, before/after restoration JSON and diagnostic ZIP. The script may exit 0 with SKIPs; each claimed feature must have an actual PASS.

### H6 — 24/72-hour physical soak

`hardware-soak.yml` has `authorized_bench` and an example default VISA resource; **replace that default** with the independently verified real address. Use 24h for the stable-release minimum or 72h when explicitly required, sufficient disk, no PC sleep/reboot and no competing scope users. After the runner finishes, validate the **complete** report:

```bash
python scripts/validate_soak_report.py \
  --report-dir qualification_reports/soak/dpo4054-24h \
  --min-hours 24 --expected-commit "$(git rev-parse HEAD)"
```

Use the *actual* report directory when the workflow writes `hardware_verification_reports/soak-24h-<run_number>`. The validator must reject incomplete/cancelled/one-cycle/short runs, missing initial/final readings, inconsistent monotonic/wall duration, deadline gaps, resource growth or cleanup failures. **A green 24h workflow and retained independently reviewed report are both required.** No synthetic 24h report can substitute for physical evidence.

### H7 — USB/TCPIP R0-F/R0-T comparison (release/performance)

This is **not an automatic PR Actions workflow**. Follow `docs/r0-usb-tcpip-qualification.md` and `docs/p0-qualification-runbook.md`. Both `capture_r0_baseline.py` and `compare_r0_baseline.py` issue reversible setup writes; obtain explicit approval and confirmed restore plan. On independently approved known-good commit, collect immutable **separate USB and TCPIP** baseline JSON, threshold review and additional measured metrics. On final candidate SHA compare against the matching transport using:

```bash
python scripts/compare_r0_baseline.py \
  --resource "$DPO4000_USB_RESOURCE" \
  --expected-idn "$DPO4000_VERIFIED_IDN" \
  --baseline-dir qualification_reports/performance/usb/baseline \
  --thresholds tests/baselines/r0_timing_thresholds.json \
  --output-dir qualification_reports/performance/usb/candidate \
  --authorize-reversible-writes --confirm-restore-plan

python scripts/report_r0_transports.py \
  --root qualification_reports/performance \
  --thresholds tests/baselines/r0_timing_thresholds.json \
  --approval threshold_review.json
```

Repeat comparison for TCPIP with its resource and `tcpip` directories. **Accept only:** raw `samples_s` distributions, min/p50/p95/max recomputable from raw samples, 1k/10k/100k/1M coverage, zero unreviewed errors/timeouts, transport+identity match, hashes of immutable baselines, approved threshold SHA-256, `r0_extra_metrics.json` and PASS transport-comparison output. Any uncovered operation or missing threshold is BLOCKED; do not synthesize extra observations or silently increase thresholds.

### H8 — P0 release evidence / qualified human review

Only for an actual stable release, arrange the complete candidate evidence at `qualification_reports/` and run the **offline** fail-closed validator (no physical I/O):

```bash
python scripts/evaluate_p0_release.py \
  --root qualification_reports --expected-commit "$(git rev-parse HEAD)"
```

The evaluator requires `software/ci.json` (all final-head hosted jobs), `hardware/qualification.json` with per-case artifact hashes and setup restoration, both transport performance baselines/candidates, `soak/soak_report.{json,md}`, `a25/` qualification evidence and `review.json` with an actual independent qualified human approval. It creates `manifest.json`, `summary.json` and `summary.md`. Only **all required gates PASS**, an independently verified genuine Actions/HIL provenance and human review permit stable publication. `docs/p0-qualification-runbook.md` specifies the exact machine-readable manifest schema.

## 7. Required closure packet (per PR, not per workflow)

A reviewer must post `docs/pr-closure-evidence-template.md` as a final PR comment or fill its fields in a dedicated closure section, including:

- **Identity:** PR URL/#, target base, 40-digit tested head and latest merge/rebase SHA, purpose/change class, affected paths and dependent PRs.
- **Software:** one row for *each applicable workflow/job* with required/applicable flag, conclusion, final revision, run/job URL, test PASS/FAIL/ERROR/SKIP counts, artifact links and hashes if retained, and short note on failure/skip disposition.
- **Targeted verification:** exact test command/OS/Python/dependency constraints and stdout/JUnit/JSON evidence (for local-only results; hosted CI job remains authoritative when available).
- **Security/architecture:** review of public-driver boundary, raw SCPI restrictions, session ownership, authn/authz, sample/record limits, error handling and cancellation where relevant.
- **Physical:** permission category and independent operator approval; resource/serial/firmware/options/fixture; transport; HIL workflow or script, run ID, before/after setup match, per-case outcome, raw measurement/artifact evidence, and SKIP reasoning. If not run, state `NOT_RUN` and mark any HIL-dependent claim BLOCKED.
- **Release-specific:** immutable USB/TCPIP comparison/threshold review, 24h soak validator, A25 report, SBOM/SHA256, P0 evaluator summary and independent qualified reviewer approval.
- **Decision:** PASS/BLOCKED/FAIL, remaining P0/P1 findings with file+line and remedy, exact accepted scope, reviewer identity/date, merge commit or closed-unmerged reason.

**Closure must be truthful:** a PR implementing code behind a non-hardware feature flag may be merged with explicitly deferred hardware qualification when the feature is not claimed hardware-ready; a PR claiming hardware qualification or a stable release cannot.

## 8. Reviewer sequence for every PR

1. Read the diff and independent review comments; classify the change using Section 2 and enumerate all workflow gates from Section 3 plus any new workflow on the PR branch.
2. Verify **all code and tests actually exist at the final head**; identify added/changed interfaces, raw-SCPI/driver/Qt boundary, and feature-specific tests. If test coverage is missing, block or add cases; do not accept a generic management-level checklist as a technical review.
3. Inspect hosted Actions conclusion and complete artifact evidence at the final PR head (Section 5). Re-run relevant CI if the head, dependency, workflow or baseline changed.
4. Run/review any approved HIL (Section 6). If no physical permission/bench, leave physical qualification as BLOCKED/NOT_RUN. No AI agent may treat simulated HIL as real.
5. Publish the closure packet, linking failing lines and disposition. Record independent human approval for P0/physical release claims; do not self-certify.
6. Merge only under repository review/branch-protection policy, then inspect the new main SHA. Close without merge only with an explicit superseded/abandoned rationale. When relevant, verify the Pages push job after merge.

## 9. Current repo-specific technical gaps (must not be silently waived)

| Location | Observed issue | Required follow-up |
|---|---|---|
| `.github/workflows/a22-hil-qualification.yml`, `.github/workflows/a25-headless-hil.yml` | Unlike hardware API and soak, these don't declare the shared physical-bench concurrency lock | Add the shared group in a separately reviewed hardware-workflow hardening PR; until then enforce exclusive manual reservation |
| `.github/workflows/a25-headless-hil.yml` | Dispatch has resource and IDN only, **no explicit bench authorization input** | Add fail-closed approval/preflight; require documented operator approval prior to any interim manual execution |
| `.github/workflows/build-gui-executables.yml` | Packaging workflow uses path filters and release publishing is conditional on tags/dispatch | Document NOT_APPLICABLE only if change scope doesn't affect packaging; publishing a release is never implied by a PR build |
| `docs/p0-qualification-runbook.md` (legacy snippet) | Earlier read-only instructions omitted required `--authorize-read-only`, serial/options and named an unrestricted hardware pytest directory | This PR corrects the snippet and directs to the reviewed read-only hardware subset |
| `docs/dpo4054-readonly-hil.md` | Concurrency group text named `dpo4000-exclusive-bench`, workflow actually uses `dpo4000-physical-bench` | This PR corrects the text |
| `docs/automation-logger-hil.md` | Historical example checked out an old test branch and contained a sample IP as if bench-specific | This PR switches to exact candidate SHA and explicit operator-supplied VISA resource |
| PR #80 MCP proposal | New gateway only serializes within its process; Desk ownership and MCP HTTP auth are not implemented | Do not claim live shared-session qualification; require DPO-MCP-02 integration and new offline/HIL evidence |

## References

- `docs/p0-qualification-runbook.md` — P0 release gate and offline release manifest.
- `docs/p0-independent-review.md` — independent safety and CI provenance findings.
- `docs/dpo4054-readonly-hil.md` — strict query-only physical admission and safe test subset.
- `docs/hardware-api-tests.md` and `docs/hardware-verification.md` — full verifier.
- `docs/r0-usb-tcpip-qualification.md` — R0 raw timing/threshold/transport evidence.
- `docs/a22-test-matrix.md` / `docs/a25-test-matrix.md` — feature-specific gates.
- `docs/automation-logger-hil.md` — automated/logger real bench.
- `docs/pr-closure-evidence-template.md` — final PR evidence record.

**Any future CI workflow added or removed must be added/removed here as part of the same PR.** The `tests/test_ci_runbook_inventory.py` contract intentionally fails if the tracked workflow inventory and this runbook diverge.
