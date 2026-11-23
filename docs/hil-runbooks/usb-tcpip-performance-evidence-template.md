# DPO4054 USB/TCPIP R0 — empty performance qualification evidence

**TEMPLATE / NOT RUN — status BLOCKED.** Do not add fake samples, hashes, reviewer signatures or false PASS labels.

| Field | USB real device | TCPIP same real device |
|---|---|---|
| Resource / VISA backend / host | NOT_VERIFIED | NOT_VERIFIED |
| *IDN? model / exact serial / firmware / options | NOT_VERIFIED | NOT_VERIFIED |
| Approved baseline commit 40-hex SHA / candidate 40-hex SHA | NOT_RECORDED | NOT_RECORDED |
| Operator reversible-write authorization and UTC | NOT_PROVIDED | NOT_PROVIDED |
| Setup snapshot + restoration VERIFIED | NOT_RUN | NOT_RUN |
| R0 functional baseline/candidate data + SHA256 | NO_FILES | NO_FILES |
| R0 timing baseline/candidate raw samples + SHA256 | NO_FILES | NO_FILES |
| 1k/10k/100k/1M actual waveform coverage | NOT_MEASURED | NOT_MEASURED |
| Timings/sample counts/min/p50/p95/max/errors | NOT_MEASURED | NOT_MEASURED |
| r0_extra_metrics.json: transport throughput | NOT_MEASURED | NOT_MEASURED |
| Extra A15/A18/A21/A25/cancel/resources/GUI | NOT_MEASURED | NOT_MEASURED |
| Comparison_report.json and exit code | NOT_RUN | NOT_RUN |
| Approval of six baseline SHA256 and threshold SHA256 | NOT_APPROVED | NOT_APPROVED |

| Shared requirement | Status |
|---|---|
| threshold_review.json independently approved | NOT_APPROVED |
| transport_comparison.json/.csv/.md PASS | NOT_GENERATED |
| Artifact URLs/hashes, actual bench logs and human review | NOT_PROVIDED |
| Overall physical R0 qualification verdict | **BLOCKED — NOT_RUN** |

## Required follow-up

Execute both real transport campaigns in [performance qualification runbook](usb-tcpip-performance.md), gather immutable baseline/candidate observations, obtain independent threshold approval and run transport rollup. Don't claim PASS for missing/unsupported waveform sizes or unmeasured extra metrics.
