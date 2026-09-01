# Full real-hardware API verification

DPO4000 Utils v0.6.2 includes a bench qualification runner that exercises the public driver API against a connected Tektronix DPO4000-family oscilloscope and produces a permanent verification report.

The verifier is separate from normal unit tests. Unit tests continue to validate parsers, validation rules, command builders, GUI behavior, and error handling without hardware. The bench verifier answers a different question:

> Does the public `DPO4000Scope` / `DPO4054` API actually operate correctly against this physical oscilloscope, VISA stack, firmware, and installed option set?

## Verification profiles

The runner has three profiles.

| Profile | Purpose | Instrument changes |
| --- | --- | --- |
| `read-only` | Qualification without intentional setup changes | Queries, waveform reads, hardcopy capture, settings save |
| `reversible` | Exercise normal configuration setters | Adds temporary configuration writes and restores the captured startup setup afterward |
| `full` | Exercise disruptive acquisition/trigger/settings paths | Adds run/stop/single/force-trigger, settings restore, measurement clearing, and other disruptive calls; startup setup is restored afterward |

The runner captures the initial setup with `*LRN?` / `SET?` compatibility handling before write-capable cases. If a write case fails midway, restoration is still attempted in the final cleanup path.

### Reference-memory overwrite is separately guarded

`save_waveform_to_reference()` changes the contents of a REF memory. A scope setup string cannot be assumed to restore the original waveform samples.

Therefore even the `full` profile reports this method as **SKIP** unless you additionally pass:

```text
--allow-reference-overwrite
```

and deliberately select a disposable destination with:

```text
--reference-destination 4
```

Do not enable this option unless the selected REF waveform may be overwritten.

## Installation on the bench PC

The PC must have:

- Python 3.10 or newer;
- the repository checkout;
- PyVISA;
- a working VISA runtime/backend such as NI-VISA, TekVISA, or Keysight VISA;
- USB or LAN access to the oscilloscope.

Install the development environment:

```bash
python -m pip install -e .[dev]
```

Confirm that the VISA resource is visible if needed:

```python
from dpo4000_utils import list_visa_resources

print(list_visa_resources())
```

## Recommended qualification sequence

Use the actual resource shown by your VISA installation. For the development DPO4054 it may look like:

```text
USB0::0x0699::0x0401::C011280::INSTR
```

### 1. Read-only qualification

Linux/macOS shell:

```bash
python scripts/run_hardware_verification.py \
  --resource 'USB0::0x0699::0x0401::C011280::INSTR' \
  --profile read-only \
  --test-channel 1 \
  --waveform-points 1000
```

PowerShell:

```powershell
python scripts/run_hardware_verification.py `
  --resource 'USB0::0x0699::0x0401::C011280::INSTR' `
  --profile read-only `
  --test-channel 1 `
  --waveform-points 1000
```

This is the safest first run. It verifies discovery/session behavior, identity, channel/measurement/trigger/acquisition/display readbacks, BUS/REF capabilities, binary waveform acquisition, hardcopy capture, and settings save.

### 2. Reversible write qualification

After the read-only run is clean:

```bash
python scripts/run_hardware_verification.py \
  --resource 'USB0::0x0699::0x0401::C011280::INSTR' \
  --profile reversible \
  --test-channel 1 \
  --waveform-points 1000
```

This additionally exercises reversible public setters/configurators for:

- channel label/configuration;
- measurements;
- MATH;
- horizontal position;
- acquisition configuration;
- edge trigger;
- display/message;
- REF display configuration;
- BUS common configuration when BUS capability is present;
- legacy waveform CSV methods.

The original scope setup is reapplied at the end even if a write-capable case fails.

### 3. Full disruptive qualification

```bash
python scripts/run_hardware_verification.py \
  --resource 'USB0::0x0699::0x0401::C011280::INSTR' \
  --profile full \
  --test-channel 1 \
  --waveform-points 1000
```

This adds methods that intentionally alter acquisition/trigger execution state or restore a setup file. The startup setup is reapplied after the run.

Without REF-overwrite authorization, the report intentionally leaves `save_waveform_to_reference()` as **SKIP** and the command exits with code `2` to indicate that destructive API coverage is incomplete.

To qualify that final method using a disposable REF4:

```bash
python scripts/run_hardware_verification.py \
  --resource 'USB0::0x0699::0x0401::C011280::INSTR' \
  --profile full \
  --test-channel 1 \
  --waveform-points 1000 \
  --allow-reference-overwrite \
  --reference-destination 4
```

## Waveform record-length matrix

For Phase-4 waveform qualification, repeat a read-only or reversible run with increasing transfer sizes:

```bash
--waveform-points 1000
--waveform-points 10000
--waveform-points 100000
--waveform-points <largest practical configured record length>
```

The structured waveform test caps its point count to the current scope record length. The legacy CSV evidence path uses a small temporary record length by default to avoid creating unnecessarily large report artifacts; control it with:

```text
--artifact-record-length 1000
```

## Generated evidence

Unless `--output-dir` is supplied, each run creates:

```text
hardware_verification_reports/<UTC timestamp>/
```

Typical contents are:

```text
verification_report.md
verification_report.html
verification_report.json
scope_setup_before.json
scope_setup_after_restore.json
scope_settings_driver_save.json
scope_screen.png
CH1_legacy.csv
all_channels_legacy_CH1.csv
...
all_channels_combined.csv
```

The reports record:

- package version;
- Python/platform information;
- VISA resource;
- `*IDN?` response;
- selected safety profile;
- PASS / FAIL / SKIP for each verification case;
- duration and diagnostic detail;
- every public driver method and its verification status;
- exported package functions and their verification status.

## Self-auditing API coverage

The verification implementation reflects `DPO4000Scope` at runtime and compares it with a checked-in hardware-verification manifest.

Normal CI contains a test requiring an exact match. If a future release adds a public hardware method or exported package function, CI fails until that symbol is deliberately classified and assigned a verification policy/case. This prevents an outdated verifier from claiming full API coverage.

A method can have these report states:

- **PASS**: at least one enabled hardware case exercised it successfully;
- **FAIL**: an enabled case covering it failed;
- **SKIP**: its case was deliberately not run because of profile or unavailable hardware capability;
- **UNVERIFIED**: no verification case covers it. This is considered a verifier defect and produces a failing exit code.

BUS/REF option-dependent functionality can legitimately be SKIP when the connected instrument does not expose that capability. The report preserves that distinction instead of calling the driver broken.

## Exit codes

| Code | Meaning |
| ---: | --- |
| `0` | Enabled verification completed without failures; no public symbol is unverified |
| `1` | One or more cases failed, or the public API manifest contains an unverified symbol |
| `2` | `full` profile completed, but destructive REF waveform storage was not qualified because overwrite was not explicitly authorized |

## GitHub Actions on a bench runner

`.github/workflows/hardware-api-tests.yml` can run the same verifier manually on a self-hosted bench PC labelled:

```text
self-hosted
dpo4000
```

The workflow accepts profile, test channel, waveform-point count, and REF-overwrite settings. It uploads the complete `hardware_verification_reports/` directory as a GitHub Actions artifact even when verification fails, so the diagnostic report is retained.

GitHub-hosted runners cannot perform this qualification because they cannot access the physical USB/LAN instrument or your VISA runtime.
