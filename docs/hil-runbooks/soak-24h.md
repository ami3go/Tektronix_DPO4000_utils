# HIL-02 — Continuous 24-hour (optional 72-hour) DPO4054 soak

**State: TEMPLATE / NOT EXECUTED / BLOCKED until real instrument evidence exists.** A GitHub-hosted synthetic performance test is not a soak. See [global CI/PR closure](../ci-pr-closure-runbook.md), [soak evidence form](soak-evidence-template.md) and [P0 qualification](../p0-qualification-runbook.md).

## 1. Admission and safety

- First obtain passing exact-head software CI and a verified read-only physical smoke. The soak cannot replace either.
- Reserve one **real** DPO4054 and a stable [self-hosted, dpo4000] runner for the *entire continuous test*. Independently record exact VISA resource, full `*IDN?` (including serial), firmware/options, host/backend, operator approval/UTC time.
- Disconnect/close all competing Desk, MCP, USB and TCPIP clients, disable host sleep/reboot/auto-updates, ensure sufficient disk and stable power/network. The hardware-soak workflow has the shared `dpo4000-physical-bench` lock, but A22/A25 HIL are not yet covered by it.
- Use **strictly read-only** soak workload only: no scope configuration, screenshot/transfer setup writes or deliberate fault injection. Do not modify the scope while test is underway.
- Workflow example VISA resource is **not** verified. A token or approval string must not be recorded in public artifacts. A test cannot be initiated by unapproved AI agents.

## 2. GitHub-hosted physical runner dispatch

Use [DPO4000 Hardware Soak workflow](https://github.com/ami3go/Tektronix_DPO4000_utils/actions/workflows/hardware-soak.yml) → **Run workflow** from the exact candidate branch only after operator approval.

| Input | Example selection / why |
|---|---|
| `authorized_bench` | `true` **only after** actual operator approval, otherwise STOP |
| `visa_resource` | Operator-verified real USB/TCPIP resource; replace workflow default |
| `duration_hours` | `24` for the release minimum; `72` only when separately required |
| `interval_seconds` | `10` default; script requires finite >=5 seconds |
| `max_failures` | `10` default script/workflow limit; don't relax to force PASS |
| `max_rss_growth_mib` | `256` default limit; actual growth must be recorded and reviewed |
| Branch | Exact approved head SHA verified from job checkout |

Preflight and software guard check must complete successfully before opening the VISA session. The workflow then runs `scripts/run_hardware_soak.py` and **always** executes `scripts/validate_soak_report.py`, uploads results even on failure, and fails if the independent validator reports invalid evidence.

### Local bench alternative (never run as simulated CI)

```bash
# Use only on a reserved physical bench after read-only HIL authorization.
export DPO4000_RESOURCE="<VERIFIED_REAL_DPO4054_VISA_RESOURCE>"
export QUALIFIED_SHA="$(git rev-parse HEAD)"
python scripts/run_hardware_soak.py \
  --resource "$DPO4000_RESOURCE" \
  --duration-hours 24 --interval-seconds 10 \
  --max-failures 10 --max-rss-growth-mib 256 \
  --output-dir qualification_reports/soak/dpo4054-24h

python scripts/validate_soak_report.py \
  --report-dir qualification_reports/soak/dpo4054-24h \
  --min-hours 24 --expected-commit "$QUALIFIED_SHA"
```

The local command is a **real 24-hour instrument run**, not a dry run. Do not execute without a real approved resource. For 72h substitute `--duration-hours 72` and `--min-hours 72` and a distinct output directory. The workflow writes to `hardware_verification_reports/soak-24h-<run_number>` instead; pass that actual directory to the validator.

## 3. Expected observations

At a 10-second interval, 24h corresponds to approximately **8640 scheduled opportunities**; the validator checks actual scheduled/accounted cycles, gaps and elapsed time, not a naïve exact count. A few missed deadlines may be allowed only by the predefined limit; a one-cycle record with elapsed=24h is **FAIL**. Never invent readings or stretch timestamps.

| Required item | What must be checked |
|---|---|
| `soak_report.json` | Final status PASS, actual device identity, exact source SHA, physical test time, valid numeric cycle observations and failure/timeout counts |
| `soak_report.md` | Human-readable status and same measured totals; not a standalone attestation |
| Start/end timestamps | Monotonic duration >=86,400 s and UTC wall-clock consistency within validated tolerance |
| Cycles and timing | Scheduled vs completed vs missed cycles; bounded gap, p50/p95/max and no unexplained timeouts |
| Resource health | RSS/Python growth, FD/thread growth, cleanup and last readback within configured limits |
| Setup/transport | No unapproved writes, unchanged verified configuration where measured; connection/session released after completion |
| Independent validator | `validate_soak_report.py` exit code 0, 24h minimum and matching exact SHA |
| Provenance | Self-hosted workflow URL, job/run ID, artifact URL/hash, runner identity, bench reservation and independent reviewer approval |

Read the actual `scripts/run_hardware_soak.py` and `scripts/validate_soak_report.py` when reviewing specific field names. A `RUNNING` checkpoint is not a completed soak report.

## 4. Failure, partial completion, restart policy

- `STOP/BLOCKED` for no bench approval, loss of scope ownership, identity mismatch or unapproved setup change.
- `FAIL` for short duration, early exit, unacceptable missed deadlines/timeouts, resource-growth violation, missing final query, failed cleanup, inconsistent UTC/monotonic time or failed independent validation.
- An interrupted run **cannot resume its validity from a checkpoint**. Start a completely new approved 24h campaign and preserve the failed artifact separately. Never concatenate separate runs into a fictitious continuous test.
- Do not increase failure/resource budgets or change `--min-hours` merely to obtain PASS. Every parameter change is a new approved campaign with reviewed rationale.

## 5. Closing evidence

Retrieve `dpo4000-soak-24h-<run_number>` artifact (normally 90-day retention) and fill [soak evidence template](soak-evidence-template.md) with actual raw report summaries, exact SHA, dates and hashes. Link both the runner log and independent validator step. A **PASS soak** requires valid **real bench observations**, a matching full 24h report and independent review. A success message from a code-only test is `NOT_RUN`, not PASS.
