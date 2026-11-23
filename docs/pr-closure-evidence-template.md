# PR final verification and closure evidence record

Copy this entire record into the **final PR comment**, complete every field, and link actual CI results. Use `NOT_APPLICABLE` plus explicit rationale when a gate genuinely does not apply, `NOT_RUN/BLOCKED` for missing physical evidence, and `PENDING` until checks finish. Never use a fabricated PASS.

## A. Provenance and reviewed scope

| Field | Verified value |
|---|---|
| PR / issue / dependencies | <links> |
| Base branch and SHA | `main@<40-char-sha>` |
| Exact last tested PR HEAD SHA | `<40-char-sha>` |
| Checkout / synthetic merge SHA if different | `<40-char-sha>` |
| Package / module / affected files | <paths> |
| Change classes (DOC/DEP/DRV/GUI/A22/A15-A21/A25/AUT-LOG/MCP/CI-SEC/REL) | <classes> |
| Reviewer / review link / date UTC | <identity, URL, ISO8601> |
| Required HIL? Which profile and reason? | <required/not applicable/not run> |

## B. Exact-head CI and security

| Workflow / job | Required? | Tested SHA (40 hex) | PASS/FAIL/PENDING/BLOCKED/N/A | Tests pass/fail/error/skip | Actions job URL | Artifact/JUnit link, SHA-256 | Disposition |
|---|---|---|---|---|---|---|---|
| Ruff | yes | | | | | | |
| Python Linux 3.10 | yes | | | | | | |
| Python Linux 3.11 | yes | | | | | | |
| Python Linux 3.12 | yes | | | | | | |
| Python Linux 3.13 | yes | | | | | | |
| Python Windows 3.12 | yes | | | | | | |
| PySide6 offscreen | yes | | | | | | |
| Offline R0/synthetic benchmarks | yes | | | | | | |
| CodeQL Python | yes | | | | | | |
| Read-only guard offline | yes | | | | | | |
| Build Windows ZIP | depends | | | | | | |
| Build Linux binary/packages | depends | | | | | | |
| Release integrity / SBOM / SHA256 | depends | | | | | | |
| A22 hosted synthetic | depends | | | | | | |
| MCP offline (if PR #80 branch/merged) | depends | | | | | | |
| Other new/changed checks | depends | | | | | | |

Local/offline commands, OS/Python/pinned dependency versions, exit codes and generated artifacts:

```text
<exact commands and outcomes; never replace a hosted job URL with "tests passed">
```

Security/fault/SCPI/session/serialization/GUI boundary findings, with **file:line** and proposed fixes:

```text
<finding IDs, affected location, remediation commit or justified nonapplicability>
```

## C. Physical HIL (conditionally required, always explicitly classified)

| Field | Actual observed/approved evidence |
|---|---|
| Approval + bench owner + approval link | <operator and record, or NOT_RUN> |
| Safety profile (query-only/reversible/full) | |
| Exact instrument IDN, serial, firmware, options | |
| VISA resource, USB/TCPIP, backend and runner OS | |
| Probe/fixture and record lengths | |
| Exact Actions/workflow run or local command + SHA | |
| Per-case PASS/FAIL/SKIP incl. excluded capabilities | |
| Pre/post setup SHA-256 and restoration verdict | |
| Instrument lease/session cleanup verdict | |
| Raw measurements, timing/skew/error counts | |
| JUnit/JSON/MD/HTML/trace/record artifact URLs and hashes | |
| Hardware qualification decision | PASS / FAIL / BLOCKED / NOT_RUN |

When physical HIL is **not** necessary for the scope of this PR, write `NOT_APPLICABLE` with a *technical reason*; when hardware behavior is claimed and HIL was not run, write `BLOCKED`, not `NOT_APPLICABLE`.

## D. Additional P0/release qualification (only when applicable)

| Gate | Evidence path, exact commit and independent reviewer | PASS/FAIL/BLOCKED |
|---|---|---|
| Exact-head software/CI manifest | `qualification_reports/software/ci.json` | |
| Public API hardware cases and setup integrity | `qualification_reports/hardware/qualification.json` | |
| R0 USB baseline + real candidate raw timings | `qualification_reports/performance/usb/` | |
| R0 TCPIP baseline + real candidate raw timings | `qualification_reports/performance/tcpip/` | |
| Approved threshold hashes + transport rollup | `qualification_reports/performance/transport_comparison/` | |
| Continuous >=24h soak + independent validator | `qualification_reports/soak/` | |
| A25 installed CLI, API, second-session evidence | `qualification_reports/a25/` | |
| P0 evaluator manifest/summary | `qualification_reports/manifest.json`, `summary.json`, `summary.md` | |
| Qualified independent human approval | `qualification_reports/review.json` + external review URL | |

## E. Closure decision

- **Decision:** MERGE_APPROVED / BLOCKED / CLOSED_UNMERGED.
- **Acceptance scope:** exact features and restrictions actually verified.
- **Remaining P0/P1:** issue link, file:line, responsible follow-up, next test.
- **CI exceptions:** each waived/not-applicable gate, reason and approving reviewer.
- **Hardware assertion:** actual HIL PASS / NOT_RUN / BLOCKED, never inferred from CI.
- **Merge commit or unmerged closure reason:** link and final SHA.
- **Independent sign-off:** review URL and UTC time.

See `docs/ci-pr-closure-runbook.md` for commands and the workflow decision matrix.
