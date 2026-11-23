# DPO4054 Physical HIL — empty operator evidence form

**TEMPLATE / NOT RUN — status BLOCKED; this is not a PASS certificate.** Copy into the authorized PR's closure record after actual execution.

| Field | Real observation / reference |
|---|---|
| PR / exact 40-hex candidate SHA / reviewed feature | TO_RECORD |
| Approval operator/UTC/review URL | NOT_PROVIDED |
| Profile: read-only / reversible / full / REF overwrite | NOT_SELECTED |
| Bench / self-hosted job URL + run/job ID | NOT_RUN |
| USB or TCPIP VISA resource / backend / OS | NOT_VERIFIED |
| Actual DPO4054 *IDN? / serial / firmware / options | NOT_VERIFIED |
| CH1 Probe Comp stimulus/record length (if required) | NOT_VERIFIED |
| Before/after setup SHA256 and restore verdict | NOT_RUN |
| Exclusive VISA lock + scope released | NOT_RUN |
| Hardware verifier exit code / report.json/.md/.html | NOT_RUN |
| Pytest JUnit tests pass/fail/error/skip | NOT_RUN |
| Required cases PASS/FAIL/SKIP and real numeric readings | NOT_RUN |
| Artifacts ZIP / SHA-256 / provenance links | NOT_RECORDED |
| Review findings file:line + independent reviewer | NOT_REVIEWED |
| Verdict (only after evidence and reviewer acceptance) | **BLOCKED — NOT_RUN** |

## Required follow-up

1. Complete [physical HIL runbook](physical-hil.md) with operator authorization.
2. Attach actual waveform/measurement, raw JUnit and verifier report, setup/cleanup proof.
3. If claims remain untested, retain BLOCKED; do not change this form to PASS.
