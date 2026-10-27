# A22 test matrix and qualification evidence

Baseline main: `8a5b6cfcf794104a3f428799bd415874a8392d72`.
Baseline [Tests run 39979418992](https://github.com/ami3go/Tektronix_DPO4000_utils/actions/runs/39979418992):
Python 3.10, 3.11, 3.12, 3.13, Ruff and PySide6 all passed.

Status notation: PASS means verified by completed run; PENDING means no
qualifying evidence yet, not an implied pass.

| Gate | Automated path | Current qualification |
|---|---|---|
| 1/2/4-channel config and complete-group integrity | `tests/test_a22_live_stream.py` | Software PASS; final-head CI required |
| Partial/misaligned group rejection | `tests/test_a22_live_stream.py` | Software PASS; final-head CI required |
| Config finite/ranges | `tests/test_a22_live_stream.py` | CI required |
| State Start/Pause/Resume/Stop/Restart | `test_a22_live_stream*.py` | CI required |
| Single in flight / slow driver | `test_a22_live_stream_scheduler.py` | CI required |
| Monotonic absolute deadlines and misses | `test_a22_live_stream_scheduler.py` | CI required |
| Generation stale-success/failure and paused-frame suppression | `test_a22_live_stream_scheduler.py` | Final-head CI required |
| Latest frame/backpressure | `test_a22_live_stream_scheduler.py` | CI required |
| Spike-preserving min/max | `test_a22_live_stream.py` | CI required |
| Driver boundary, Stop-in-flight lease, dispatch exceptions | `test_a22_live_stream_safety.py`, `test_a22_live_stream_gui_contract.py` | Final-head CI required |
| Production Live page, large central canvas, CH1–CH4 controls | `test_a22_live_stream_gui_contract.py` | Software PASS; final-head CI required |
| GUI 50ms heartbeat with synthetic four-channel activity | `test_a22_live_stream_gui_heartbeat.py` | Software PASS; final-head CI required |
| Synthetic 1k / 10k / 100k / 1M | Permanent `Tests` PySide6 job / benchmark artifact | Final-head CI required |
| Linux/Windows package startup | existing release build workflows | CI required |
| CH1 1k/10k/100k USB | Reversible-write authorized HIL, mandatory DATA snapshot/restore | **Bench PASS** (2026-10-26, non-RC commit, see below); 1M **PENDING** |
| CH1 1k/10k/100k TCPIP | Separate reversible-write authorized HIL resource/run | **Bench PASS** (2026-10-26, non-RC commit, see below); 1M **PENDING** |
| CH1–CH4 complete groups, USB | `DPO4000_A22_MULTI_CHANNELS=YES` hardware test | **Bench PASS** at 1k/10k/100k (non-RC commit); **PENDING exact-head run** |
| CH1–CH4 complete groups, TCPIP | Same test on separate TCPIP resource | **Bench PASS** at 1k/10k/100k (non-RC commit); **PENDING exact-head run** |
| 30–60 min soak (CH1/10k/5Hz) | Opt-in bench, JSON memory metrics and setup restoration | **PENDING** |
| 12 h four-channel Live View soak (TCPIP) | `scripts/run_live_view_soak.py`, validated with `--validate-report` | **IN PROGRESS** (started 2026-10-26 17:32 UTC on commit `059bb10`; no result yet, so not qualification evidence) |
| Same soak over USB | same script, USB resource | **PENDING** (USB link needs a physical replug first) |
| Physical GUI heartbeat / shared-session conflict | Supervised GUI and instrument verification | **PENDING** |
| Timeout / disconnect physical negative tests | Authorized fault injection and verified cleanup | **PENDING** |
| Independent reviewer approval | Human reviewer not author | **PENDING** |

## Bench results, 2026-10-26 (not release-candidate evidence)

DPO4054 `C011280`, FV v2.68, record length 100,000, all four channels fed from the
internal generator (~2.6 Vpp square wave). Code at `934aa97` (single `WFMOUTPRE?`
preamble read); hardware test harness `23c505c`. 30 s per case, requested rate 5
groups/s, `GITHUB_SHA` recorded in each JSON. A full `SET?` snapshot (492 lines)
was identical before and after each transport's run and the `DATA:*` restoration
JSON reported `verified: true`. The JSON evidence is **not committed** (`*.json`
is git-ignored); it was retained on the bench PC only. These are bench
measurements, not reviewed baselines, and not an exact-head release run.

Single-channel suite (sustained 1k/10k/100k, Stop during transfer, Pause/Resume):
5 passed, 1 skipped on **both** transports. The skip is 1M points: the scope record
was 100,000 and A22 never changes it.

Complete sequential groups, 0 errors in every case (p50/p99 are group cycle time;
skew is first-to-last channel read):

| Ch | Points | USB groups/s | USB p50/p99 ms | USB skew ms | TCPIP groups/s | TCPIP p50/p99 ms | TCPIP skew ms |
|---|---|---|---|---|---|---|---|
| 1 | 1k | 5.00 | 174 / 185 | 0 | 5.00 | 170 / 174 | 0 |
| 1 | 10k | 5.00 | 175 / 190 | 0 | 4.97 | 178 / 192 | 0 |
| 1 | 100k | 2.53 | 212 / 221 | 0 | 2.50 | 259 / 316 | 0 |
| 2 | 1k | 2.50 | 326 / 336 | 158 | 2.50 | 319 / 338 | 151 |
| 2 | 10k | 2.50 | 342 / 359 | 164 | 2.49 | 341 / 387 | 160 |
| 2 | 100k | 1.79 | 407 / 463 | 192 | 1.65 | 496 / 754 | 401 |
| 4 | 1k | 1.26 | 666 / 673 | 479 | 1.26 | 645 / 656 | 470 |
| 4 | 10k | 1.25 | 685 / 710 | 515 | 1.25 | 678 / 706 | 493 |
| 4 | 100k | 1.05 | 804 / 836 | 591 | 0.95 | 988 / 1030 | 740 |

### After the preamble cache (TCPIP only; commit `0ab4429`)

Same bench, same method, with the production Live View path (one `WFMOUTPRE?`
query, cached preamble, raw-bytes decode; `preamble_cache: true` in each JSON).
0 errors in every case; `SET?` identical before/after and the `DATA:*` restore
verified. **USB was not re-run**: the USB link was already desynchronised when the
run started (all setup steps errored), so USB has only the pre-cache numbers above.

| Ch | Points | groups/s | p50 / p99 ms | skew ms |
|---|---|---|---|---|
| 1 | 1k | 4.97 | 117 / 187 | 0 |
| 1 | 10k | 4.93 | 124 / 200 | 0 |
| 1 | 100k | 3.73 | 194 / 277 | 0 |
| 2 | 1k | 2.73 | 207 / 348 | 92 |
| 2 | 10k | 2.53 | 225 / 366 | 99 |
| 2 | 100k | 2.30 | 371 / 558 | 169 |
| 4 | 1k | 2.20 | 388 / 570 | 279 |
| 4 | 10k | 1.77 | 409 / 712 | 279 |
| 4 | 100k | 1.17 | 717 / 1098 | 498 |

Compared with the pre-cache TCPIP rows, one four-channel 100k group dropped from
about 990 ms to about 720 ms (p50). Bench measurements only, not reviewed baselines.

Reading the table: at 1 channel the 5 groups/s request is the limit up to 10k
points; beyond that, and for every extra channel, the sequential per-channel cost
(about 165 ms at 1k, about 210–260 ms at 100k) sets the rate. USB and TCPIP match
at small records; USB is faster and steadier at 100k. Channel skew is a property of
sequential reads and grows with channel count.

Reproduce: `DPO4000_A22_MULTI_SOURCES=CH1,CH2` and `DPO4000_A22_MULTI_POINT_COUNT`
select channels and size for the multi-channel test (default CH1..CH4); evidence
files are named `a22-<n>-channel-<transport>-<points>.json`.

**Prerequisite:** each point count needs `HORIZONTAL:RECORDLENGTH` at least that large, set by the operator before the run (A22 never changes the record length; the DATA:* restoration evidence covers only the DATA registers). A count the scope cannot supply is reported as SKIP with the required setting, never as PASS, so the 1M row stays unqualified until it is run with a 1M record. The pause/resume and stop-in-flight tests use 10,000 points.

Real hardware qualification records are transport-scoped JSON files. Required
fields: target/actual FPS, point count, transfer latency p50/p95/p99,
samples/s, MB/s, missed deadlines, replacement and errors, scope identity,
RSS/Python allocation growth, and final driver usability. A separate DATA setup
restoration JSON with `verified: true` is mandatory. The waveform read performs
reversible DATA:* writes: a read-only scope authorization does not permit HIL. Report USB and TCPIP baselines separately.

The synthetic benchmark is deliberately **not** a real oscilloscope
throughput or VISA performance measurement. Never substitute it for HIL.

Candidate responsive-GUI gate: QTimer heartbeat 50 ms for at least 10 s;
measured p95/p99 lateness must be reported, with p99 <250 ms and worst-case
<1000 ms. This is a conservative provisional CI threshold; revise only with
real baseline evidence from runner noise and documented reasoning.

The A22 stable-release gate additionally requires the accumulated
A14/A15/A16/A18/A20/A21/A25 regressions, all four Python versions, Ruff,
offscreen PySide6 and Linux/Windows packaging to remain passing.
