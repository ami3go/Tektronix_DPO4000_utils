# DPO4054 24-hour/72-hour soak — empty operator evidence form

**TEMPLATE / NOT RUN — status BLOCKED.** A time estimate, simulated clock or test fixture cannot qualify a real continuous 24-hour soak.

| Field | Real observation / reference |
|---|---|
| PR / exact candidate SHA / branch | TO_RECORD |
| Operator + bench authorization/UTC | NOT_PROVIDED |
| Scope identity/serial/firmware / VISA backend | NOT_VERIFIED |
| Runner and workflow run/job/artifact URL | NOT_RUN |
| Required duration 24/72 hours | 24h PLANNED, NOT RUN |
| Real start UTC / end UTC / monotonic elapsed seconds | NOT_MEASURED |
| Interval seconds / scheduled cycles / completed / missed deadlines | NOT_MEASURED |
| Actual failure/timeout counts / initial/final query | NOT_MEASURED |
| RSS, Python allocations, FD/thread growth | NOT_MEASURED |
| Cleanup / independent scope release / setup consistency | NOT_VERIFIED |
| soak_report.json SHA-256 + soak_report.md URL | NO_FILES |
| validate_soak_report.py exit code / log URL / min-hours | NOT_RUN |
| Independent human reviewer / acceptance URL | NOT_REVIEWED |
| Verdict | **BLOCKED — NOT_RUN** |

## Required follow-up

Read [24-hour soak runbook](soak-24h.md), reserve the bench, execute one uninterrupted real run and independently validate final reports. Keep failed/checkpoint/incomplete artifacts with FAIL/BLOCKED status.
