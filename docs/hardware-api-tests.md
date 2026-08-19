# Hardware API tests

The repository includes an opt-in pytest suite for a real Tektronix DPO4000-family oscilloscope.
These tests are skipped during normal CI and normal local `pytest` runs unless hardware access is explicitly enabled.

## What is tested

Read-only tests run by default when hardware mode is enabled:

- open the configured VISA resource through `DPO4054`,
- read `*IDN?`,
- read CH1..CH4 labels through the public channel API,
- read CH1 trigger level through the public trigger API,
- clear and read `*ESR?` for basic SCPI status sanity.

One optional write test is available:

- temporarily set one channel label,
- verify the readback,
- restore the original label in a `finally` block.

The write test is disabled unless `DPO4000_ENABLE_WRITE_TESTS=1` is set.

## Local bench run

Install the package on a PC with a VISA runtime and the scope connected:

```bash
pip install -e .[dev]
```

Run read-only hardware tests:

```bash
DPO4000_HARDWARE=1 \
DPO4000_RESOURCE='USB0::0x0699::0x0401::C011280::INSTR' \
pytest -q -m hardware tests/hardware
```

Run with the optional label write/restore test:

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

## Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `DPO4000_HARDWARE` | unset | Must be `1`, `true`, `yes`, or `on` to run real hardware tests. |
| `DPO4000_RESOURCE` | `USB0::0x0699::0x0401::C011280::INSTR` | VISA resource name. |
| `DPO4000_TIMEOUT_MS` | `20000` | VISA timeout used by the test session. |
| `DPO4000_EXPECT_IDN` | `TEKTRONIX` | Substring expected in `*IDN?`. |
| `DPO4000_ENABLE_WRITE_TESTS` | unset | Enables the label write/restore test. |
| `DPO4000_TEST_CHANNEL` | `1` | Channel used by the optional write test. |
| `DPO4000_TEST_LABEL` | `API_TEST` | Temporary label used by the optional write test. |

## GitHub Actions

The workflow `.github/workflows/hardware-api-tests.yml` is manual-only.
It requires a self-hosted runner with labels:

```text
self-hosted
dpo4000
```

The runner must be a bench PC that can see the scope through VISA. GitHub-hosted runners cannot run these tests because they do not have access to USB/LAN bench equipment or the required VISA runtime.

Start it from **Actions → Hardware API Tests → Run workflow**, then enter the VISA resource and choose whether to enable write tests.
