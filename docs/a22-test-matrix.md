# A22 test matrix and qualification evidence

Baseline main: `8a5b6cfcf794104a3f428799bd415874a8392d72`.
Baseline [Tests run 39979418992](https://github.com/ami3go/Tektronix_DPO4000_utils/actions/runs/39979418992):
Python 3.10, 3.11, 3.12, 3.13, Ruff and PySide6 all passed.

Status notation: PASS means verified by completed run; PENDING means no
qualifying evidence yet, not an implied pass.

| Gate | Automated path | Current qualification |
|---|---|---|
| Config finite/ranges | `tests/test_a22_live_stream.py` | CI required |
| State Start/Pause/Resume/Stop/Restart | `test_a22_live_stream*.py` | CI required |
| Single in flight / slow driver | `test_a22_live_stream_scheduler.py` | CI required |
| Monotonic absolute deadlines and misses | `test_a22_live_stream_scheduler.py` | CI required |
| Generation stale-success/failure and paused-frame suppression | `test_a22_live_stream_scheduler.py` | Final-head CI required |
| Latest frame/backpressure | `test_a22_live_stream_scheduler.py` | CI required |
| Spike-preserving min/max | `test_a22_live_stream.py` | CI required |
| Driver boundary, Stop-in-flight lease, dispatch exceptions | `test_a22_live_stream_safety.py`, `test_a22_live_stream_gui_contract.py` | Final-head CI required |
| PySide6 layout, lifecycle, callbacks | `test_a22_live_stream_gui_contract.py` | CI required |
| GUI 50ms heartbeat with synthetic activity | `test_a22_live_stream_gui_heartbeat.py` | CI required |
| Synthetic 1k / 10k / 100k / 1M | Permanent `Tests` PySide6 job / benchmark artifact | Final-head CI required |
| Linux/Windows package startup | existing release build workflows | CI required |
| CH1 1k/10k/100k/1M USB | Reversible-write authorized HIL, mandatory DATA snapshot/restore | **PENDING** |
| CH1 1k/10k/100k/1M TCPIP | Separate reversible-write authorized HIL resource/run | **PENDING** |
| CH2–CH4 | future HIL profile | **PENDING** |
| 30–60 min soak (CH1/10k/5Hz) | Opt-in bench, JSON memory metrics and setup restoration | **PENDING** |
| Physical GUI heartbeat / shared-session conflict | Supervised GUI and instrument verification | **PENDING** |
| Timeout / disconnect physical negative tests | Authorized fault injection and verified cleanup | **PENDING** |
| Independent reviewer approval | Human reviewer not author | **PENDING** |

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

The A22 production merge gate additionally requires the accumulated
A14/A15/A16/A18/A20/A21/A25 regressions, all four Python versions, Ruff,
offscreen PySide6 and Linux/Windows packaging to remain passing.
