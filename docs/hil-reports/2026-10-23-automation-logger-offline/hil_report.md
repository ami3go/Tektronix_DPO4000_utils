# DPO4000 Automation + Logger Probe Comp HIL

**Status:** PASS
**Resource:** `TCPIP0::192.168.0.5::INSTR`
**IDN:** `TEKTRONIX,DPO4054,C011280,CF:91.1CT FV:v2.68 DPO4AUTO:V1.00`
**PASS/FAIL/SKIP:** 23 / 0 / 1

| Case | Group | Status | Duration | Detail |
|---|---|---|---:|---|
| `fixture-probe-comp` | fixture | **PASS** | 0.755s | Probe Comp detected CH1: 1000.1 Hz, 2.518 Vpp |
| `A1-periodic-image` | automation | **PASS** | 1.247s | A1 capture + no-overlap passed |
| `A2-image-on-trigger` | automation | **PASS** | 1.331s | A2 trigger=SAVE elapsed=0.360s |
| `A3-image-csv-trigger` | automation | **PASS** | 1.745s | A3 points=1000 trigger=SAVE |
| `A4-timed-waveform` | automation | **PASS** | 0.483s | A4 points=1000 |
| `A5-measurement-log` | automation | **PASS** | 0.323s | A5 three rows; last={1: '999.7544E+0', 2: '2.5177'} |
| `A6-conditional` | automation | **PASS** | 0.502s | A6 fired value=999.754 |
| `A7-burst` | automation | **PASS** | 1.558s | A7 two-event fresh-Single CSV burst passed |
| `A8-limits` | automation | **PASS** | 0.000s | A8 exact boundary: Maximum event count reached (2) |
| `A9-retention` | automation | **PASS** | 0.018s | A9 reclaimed=300B |
| `A10-profiles` | automation | **PASS** | 0.001s | A10 profile round-trip passed |
| `A11-reconnect` | automation | **PASS** | 3.994s | A11 disconnect/reconnect primitive passed; physical cable fault injection not automated |
| `A12-report` | automation | **PASS** | 0.004s | A12 durable event + summary passed |
| `logger-waveform` | logger | **PASS** | 0.958s | Waveform BOTH format records=2 rotations=1 |
| `logger-measurements` | logger | **PASS** | 0.021s | Measurement Logger records=3 last={1: 1000.0, 2: 2.5184} |
| `logger-mixed` | logger | **PASS** | 0.787s | Mixed fresh-Single trigger=SAVE |
| `logger-math` | logger | **PASS** | 0.696s | MATH Logger captured 1000 points |
| `logger-bus` | logger | **SKIP** | 0.000s | Decoded BUS extraction is unqualified; Probe Comp -> CH1 cannot qualify serial decode |
| `logger-buffer-health` | logger | **PASS** | 0.019s | Buffer overflow + health + writer thread passed; written=2; effective_rate=1.000/s |
| `logger-recovery` | logger | **PASS** | 0.794s | Logger recovery reconnect primitive passed; physical transport-fault injection is intentionally not automatic |
| `logger-profile` | logger | **PASS** | 0.002s | Logger profile round-trip passed |
| `logger-retention` | logger | **PASS** | 0.019s | Logger retention reclaimed=300B |
| `logger-report` | logger | **PASS** | 0.005s | Logger event/checkpoint/final report passed |
| `scope-restore` | fixture | **PASS** | 3.090s | Baseline reapplied; *LRN? differs. Compare before/after JSON |

## Debug bundle

- `hil_run.log`: chronological trace
- `tracebacks/`: full Python traceback for each failed case
- `hil_report.json`: machine-readable case details
- `environment.json`: Python/package/platform snapshot
- `scope_setup_before.json` / `scope_setup_after_restore.json`: scope-state evidence
- `artifacts/`: generated PNG/CSV/DPO4LOG/profile/report evidence
- Upload the diagnostic ZIP path printed by the runner for debugging.
