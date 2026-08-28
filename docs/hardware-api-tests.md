# Hardware API tests

The repository has two complementary real-hardware validation layers for a Tektronix DPO4000-family oscilloscope.

1. **Focused pytest hardware tests** in `tests/hardware/` provide quick regression checks for connection, selected read/write paths, and binary waveform behavior.
2. **Full public API verification** through `scripts/run_hardware_verification.py` inventories the complete public driver API, runs profile-controlled bench checks, restores the initial setup after write-capable runs, and generates Markdown/HTML/JSON evidence.

Both layers are skipped during normal local/CI test execution unless a physical scope is explicitly used.

For release qualification, use the full verifier described in `docs/hardware-verification.md`.

## Focused pytest hardware checks

The pytest hardware suite currently covers:

- opening the configured VISA resource through `DPO4054`;
- reading `*IDN?`;
- CH1..CH4 label readback;
- trigger-level readback;
- SCPI status sanity;
- deterministic binary waveform transfer;
- partial waveform/XZERO behavior;
- optional channel-label write/read/restore.

Install on the bench PC:

```bash
python -m pip install -e .[dev]
```

Run focused read-only/default hardware tests:

```bash
DPO4000_HARDWARE=1 \
DPO4000_RESOURCE='USB0::0x0699::0x0401::C011280::INSTR' \
pytest -q -m hardware tests/hardware
```

Run the optional label write/restore test too:

```bash
DPO4000_HARDWARE=1 \
DPO4000_ENABLE_WRITE_TESTS=1 \
DPO4000_TEST_CHANNEL=1 \
DPO4000_RESOURCE='USB0::0x0699::0x0401::C011280::INSTR' \
pytest -q -m hardware tests/hardware
```

On Windows PowerShell:

```powershell
$env:DPO4000_HARDWARE = "1"
$env:DPO4000_RESOURCE = "USB0::0x0699::0x0401::C011280::INSTR"
pytest -q -m hardware tests/hardware
```

## Full public API verification

Start with the safest profile:

```bash
python scripts/run_hardware_verification.py \
  --resource 'USB0::0x0699::0x0401::C011280::INSTR' \
  --profile read-only \
  --test-channel 1 \
  --waveform-points 1000
```

Then qualify reversible setter/configuration methods:

```bash
python scripts/run_hardware_verification.py \
  --resource 'USB0::0x0699::0x0401::C011280::INSTR' \
  --profile reversible \
  --test-channel 1 \
  --waveform-points 1000
```

Finally, run the disruptive profile if appropriate for the bench:

```bash
python scripts/run_hardware_verification.py \
  --resource 'USB0::0x0699::0x0401::C011280::INSTR' \
  --profile full \
  --test-channel 1 \
  --waveform-points 1000
```

`save_waveform_to_reference()` is deliberately not exercised unless a disposable REF slot is explicitly authorized. See `docs/hardware-verification.md` before enabling that test.

The verifier creates `hardware_verification_reports/<timestamp>/` containing the human-readable report, machine-readable JSON, startup/restored setup evidence, screenshot evidence, and waveform CSV artifacts.

## Focused pytest environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `DPO4000_HARDWARE` | unset | Must be `1`, `true`, `yes`, or `on` to run focused real-hardware pytest tests. |
| `DPO4000_RESOURCE` | legacy development resource | VISA resource name. |
| `DPO4000_TIMEOUT_MS` | `20000` | VISA timeout used by the focused pytest session. |
| `DPO4000_EXPECT_IDN` | `TEKTRONIX` | Substring expected in `*IDN?`. |
| `DPO4000_ENABLE_WRITE_TESTS` | unset | Enables the focused label write/restore test. |
| `DPO4000_TEST_CHANNEL` | `1` | Analog channel used by focused hardware tests. |
| `DPO4000_TEST_LABEL` | `API_TEST` | Temporary label used by the focused write test. |
| `DPO4000_WAVEFORM_POINTS` | `1000` | Binary waveform points used by the focused waveform test. |

## GitHub Actions

`.github/workflows/hardware-api-tests.yml` is manual-only and requires a self-hosted bench runner labelled:

```text
self-hosted
dpo4000
```

The workflow now runs the full verifier for the selected safety profile, runs the focused pytest hardware suite, and uploads the complete verification evidence directory as an Actions artifact even when the verifier reports failure.

GitHub-hosted runners cannot perform these tests because they do not have access to the USB/LAN bench equipment or the required VISA runtime.
