# Automation + Logger Probe Comp HIL — offline run, 2026-10-23

Bench qualification of DPO4000 Desk Automation (A1–A12) and Logger paths with `scripts/run_automation_logger_hil.py`
(`docs/automation-logger-hil.md`), run with **no internet access**.

| Item | Value |
| --- | --- |
| Result | **PASS** — 23 PASS / 0 FAIL / 1 SKIP |
| Instrument | TEKTRONIX DPO4054, S/N C011280, FV v2.68 |
| Transport | `TCPIP0::192.168.0.5::INSTR` (LAN, VXI-11) via PyVISA 1.16.2 + pyvisa-py backend (no NI-VISA) |
| Fixture | Probe Comp -> CH1 (measured 1000.1 Hz, 2.518 Vpp) |
| Package | dpo4000-utils 0.8.0 checkout (main), Python 3.13, Linux |
| Network | Internet and DNS verified down (`curl` failed, no name resolution) before the run and still down after |
| Suite | `--suite all --channel 1`, 1000 waveform points |

## Notes

- `logger-bus` is a deliberate SKIP: Probe Comp cannot stimulate serial decode and decoded BUS extraction is not hardware-qualified.
- `scope-restore` reports "`*LRN?` differs". Comparing the saved `scope_setup_before.json` with `scope_setup_after_restore.json`, the only
  difference is the vertical-bar cursor positions (`VBARS:POSITION1` / `POSITION2`: -503.1 µs / 696.9 µs before, -12.0 µs / 12.0 µs after).
  All other setup lines are identical. The cursor positions were not restored exactly.
- Physical transport-fault injection (A11 / logger-recovery) is not automated; only the disconnect/reconnect primitive is exercised.
- Screenshots, CSV and DPO4LOG artifacts from the run are not committed; only the summary report. The JSON report and setup snapshots are not committed because the repository ignores `*.json`.
