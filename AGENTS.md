# Repository AI-agent and contributor instructions

This repository controls real Tektronix DPO4000-family test equipment. The
normal development workflow is **offline only**. Never open a physical VISA
session, dispatch a self-hosted hardware workflow, change a scope setting or
claim live HIL evidence without explicit operator authorization and a confirmed
exclusive bench reservation. A local fake scope, mocked VISA, synthetic
benchmark or green hosted CI job is **not** physical qualification.

## Every PR is subject to global CI/closure policy

1. Read [global CI and PR-closure runbook](docs/ci-pr-closure-runbook.md).
   Classify the PR by modified files and intended behavior; apply the **union**
   of relevant class-specific tests and all baseline checks.
2. Perform a specific technical review: list findings by priority, **file:line**,
   consequence, proposed correction and regression test. Do not substitute
   a generic management summary for source-level verification.
3. Run safe local checks where supported, then verify **completed** GitHub
   Actions on the final 40-character PR head and document checkout/merge SHA
   differences. Never cite checks from an older head as passing.
4. Never change required CI, baseline thresholds or safety checks just to
   obtain a green result. Report blocked/failed/skipped/unavailable evidence.
5. Supply [final PR evidence record](docs/pr-closure-evidence-template.md):
   exact SHA, each applicable workflow/job URL, pass/fail/error/skip counts,
   raw artifacts and hashes, security/architecture findings, permissions,
   real HIL conditions/results when relevant, and reviewer decision.
6. PRs may be closed without merge if abandoned or superseded, with rationale;
   a merged PR must meet all applicable verification gates. A physical-claim
   or stable-release PR must not merge while mandatory HIL/release evidence
   remains BLOCKED.
7. Existing `.github/PULL_REQUEST_TEMPLATE.md` requires a closure checklist;
   follow it even for automation-generated PRs.

## Instrument access restrictions

- Hosted CI must not connect to live hardware.
- Read-only **SCPI queries** are distinct from public waveform operations
  which may transmit setup-changing DATA writes. Use only approved profiles.
- Manually triggered hardware workflows require an identified DPO4054,
  exact VISA resource/model/serial/options, operator permission, exclusive
  access, relevant probe fixture and restoration/cleanup verification.
- Hardware API/soak share a runner concurrency group; A22/A25 currently
  lack that group, so **do not assume global automated bench exclusion**.
- Never expose arbitrary SCPI, raw PyVISA handles or unsafe restore/reset
  operations to remote AI tools. MCP headless ownership is not yet coordinated
  across desktop/headless processes.

Do not claim a missing result is PASS. Leave a precise blocker, supporting
evidence, and safest next **offline** verification step.
