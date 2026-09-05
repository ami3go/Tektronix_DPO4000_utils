# Full real-hardware API verification

DPO4000 Utils **v0.7.0** includes two complementary bench qualification paths for a connected Tektronix DPO4000-family oscilloscope:

1. the public-API verifier (`scripts/run_hardware_verification.py`), and
2. the long-duration read-only soak runner (`scripts/run_hardware_soak.py`).

These are intentionally separate from normal unit/GUI CI. Hosted CI verifies parsers, state machines, public-driver boundaries, Python 3.10–3.13 compatibility and PySide6 behavior without claiming access to physical hardware.

## Public API verification profiles

| Profile | Purpose | Instrument changes |
| --- | --- | --- |
| `read-only` | Qualification without intentional setup changes | Queries, waveform reads, hardcopy capture, settings save |
| `reversible` | Exercise normal configuration setters | Temporary configuration writes; startup setup restored afterward |
| `full` | Exercise disruptive acquisition/trigger/settings paths | Run/stop/single/force-trigger, restore/default and other disruptive calls; startup setup restored afterward |

The verifier captures the initial setup before write-capable cases and attempts restoration in final cleanup even after a failure.

### Reference-memory overwrite remains separately guarded

`save_waveform_to_reference()` changes REF waveform samples and cannot be assumed reversible through a setup string. Full qualification therefore leaves it **SKIP** unless both `--allow-reference-overwrite` and an explicit disposable `--reference-destination` are supplied.

## Installation on the bench PC

Requirements:

- Python 3.10 or newer;
- this repository checkout;
- PyVISA;
- NI-VISA, TekVISA, Keysight VISA or another working VISA backend;
- USB/LAN access to the oscilloscope.

For the normal developer environment:

```bash
python -m pip install -e .[dev]
```

For a release-reproducible environment use the checked-in constraints:

```bash
python -m pip install -c constraints-release.txt -e .[dev,pyside6]
```

Confirm resource discovery if needed:

```python
from dpo4000_utils import list_visa_resources
print(list_visa_resources())
```

## Recommended API qualification sequence

Example resource:

```text
USB0::0x0699::0x0401::C011280::INSTR
```

Start read-only:

```bash
python scripts/run_hardware_verification.py \
  --resource 'USB0::0x0699::0x0401::C011280::INSTR' \
  --profile read-only \
  --test-channel 1 \
  --waveform-points 1000
```

Then reversible:

```bash
python scripts/run_hardware_verification.py \
  --resource 'USB0::0x0699::0x0401::C011280::INSTR' \
  --profile reversible \
  --test-channel 1 \
  --waveform-points 1000
```

Finally, only when disruptive behavior is acceptable:

```bash
python scripts/run_hardware_verification.py \
  --resource 'USB0::0x0699::0x0401::C011280::INSTR' \
  --profile full \
  --test-channel 1 \
  --waveform-points 1000
```

To qualify a disposable REF4 as well:

```bash
python scripts/run_hardware_verification.py \
  --resource 'USB0::0x0699::0x0401::C011280::INSTR' \
  --profile full \
  --allow-reference-overwrite \
  --reference-destination 4
```

## v0.7 session and decoded-BUS coverage

The reflection manifest includes the public `configure_session()` API and the decoded-BUS capability methods. Adding another public hardware method without a verification classification is a normal-CI failure.

Decoded BUS configuration and decoded transaction extraction are distinct capabilities. The stock v0.7 driver reports decoded transaction extraction as **unsupported/unqualified** with a reason through `get_decoded_bus_capability()`. `read_decoded_bus_events()` is therefore a legitimate hardware-verification **SKIP** until a programmer-manual command path is verified on the project DPO4054. No undocumented decoder command is inferred from BUS display/configuration support.

## Waveform transfer matrix

Repeat read-only/reversible verification with increasing transfer sizes as appropriate for the bench setup:

```text
--waveform-points 1000
--waveform-points 10000
--waveform-points 100000
--waveform-points <largest practical configured record length>
```

## 24/72-hour soak qualification

v0.7 adds `scripts/run_hardware_soak.py` for long-duration read-only stability qualification. It records operation counts, failures/reconnect observations and process/resource information where available, and writes a machine-readable report suitable for retention as a CI artifact.

Use the manual self-hosted workflow:

```text
.github/workflows/hardware-soak.yml
```

on a runner labelled for DPO4000 bench access. Select the requested duration/profile in the workflow inputs. A typical direct invocation is also supported; see the script's `--help` for the exact current arguments.

**Important:** availability of the workflow/tooling is not a hardware PASS. A release may claim 24 h or 72 h qualification only when the corresponding self-hosted run against the physical DPO4054 has completed successfully and its report artifact is retained/reviewed.

## Generated verifier evidence

By default API verification creates a timestamped directory under:

```text
hardware_verification_reports/
```

Typical evidence includes Markdown/HTML/JSON verification reports, setup snapshots, hardcopy images and CSV waveform artifacts. Reports record package/platform/VISA information, identity, selected safety profile, per-case PASS/FAIL/SKIP and the status of every public hardware symbol.

## Result semantics

- **PASS** — an enabled hardware case exercised the symbol successfully.
- **FAIL** — an enabled case failed.
- **SKIP** — deliberately not executed because of profile/safety/capability.
- **UNVERIFIED** — no verification case covers the public symbol; this is a verifier defect.

Exit codes for the API verifier remain:

| Code | Meaning |
| ---: | --- |
| `0` | Enabled verification completed without failures and no public symbol is unverified |
| `1` | A case failed or the public API manifest has an unverified symbol |
| `2` | Full profile completed but destructive REF storage was not explicitly qualified |

## GitHub Actions on a bench runner

- `.github/workflows/hardware-api-tests.yml` runs API qualification manually.
- `.github/workflows/hardware-soak.yml` runs long-duration soak qualification manually.

Both require a self-hosted machine with the physical scope/VISA stack. GitHub-hosted runners cannot establish this evidence.
