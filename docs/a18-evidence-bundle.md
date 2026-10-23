# A18 Evidence Bundle

Status: **software implementation complete on `a18-evidence-bundle`; DPO4054 qualification pending**

A18 packages one recipe run and its supporting scope evidence into a single verifiable `.dpoe` archive.

## Purpose

A18 sits after A15/A16:

```text
A15 RecipeResult
      +
A16 RuleSetResult (optional)
      +
Scope PNG (optional)
      +
WaveformData (optional)
      ↓
A18 .dpoe Evidence Bundle
```

The bundle is intended to be durable, machine-verifiable test evidence. It is not a replacement for A21 scientific interchange; A18 records evidence integrity and exact raw waveform payloads, while A21 provides richer scientific import/export workflows.

## `.dpoe` format

A `.dpoe` file is a ZIP archive with exactly one top-level `manifest.json` plus only the artifact members listed by that manifest.

Example layout:

```text
manifest.json
results/recipe_result.json
results/rule_result.json
screen/scope.png
waveforms/index.json
waveforms/CH1.raw
waveforms/CH2.raw
```

The manifest schema is `dpo4000-evidence`, version `1`.

Each artifact record contains:

```json
{
  "path": "screen/scope.png",
  "kind": "scope_screen",
  "media_type": "image/png",
  "size_bytes": 12345,
  "sha256": "..."
}
```

The manifest also records:

- UTC creation timestamp;
- scope identity when available;
- recipe name and recipe state;
- A16 rule status when available;
- caller metadata;
- complete artifact inventory.

`manifest.json` intentionally does not hash itself. `EvidenceBundleResult.sha256` records the SHA-256 of the finalized whole `.dpoe` file.

## Recipe result serialization

Recipe timing, attempts, step state, and step values are stored in `results/recipe_result.json`.

Normal scalar/dataclass/mapping values are represented directly. Potentially large or non-JSON payloads are bounded:

- `bytes` become size + SHA-256 metadata rather than being duplicated into JSON;
- large arrays become type/length/hash metadata;
- long sequences use a bounded preview;
- nested values have a maximum serialization depth.

This keeps evidence metadata bounded even when a public recipe method returns a large payload.

## Rule result serialization

When A16 rules were evaluated, `results/rule_result.json` records the complete nested rule tree:

- rule ID;
- PASS / FAIL / INVALID;
- evaluation timestamp;
- actual value;
- expected condition;
- reason;
- child evaluations.

## Waveform evidence

Waveforms are stored losslessly without requiring NumPy:

- `waveforms/index.json` records source, label, transfer range, acquisition timestamp, raw sample type, byte order, sample count, and full `WaveformPreamble`;
- each `waveforms/<SOURCE>.raw` member contains exact `array.tobytes()` sample data.

The raw payload and its index are both independently covered by manifest SHA-256 entries.

## Atomic finalization

Bundle creation follows:

```text
same-directory temporary ZIP
→ write/hash artifacts
→ write manifest
→ close ZIP
→ fsync temporary archive
→ os.replace(temp, destination)
→ fsync parent directory where supported
```

If generation fails or is cancelled, the temporary file is removed. An existing destination is not replaced until the complete archive is ready.

## Verification boundary

`verify_evidence_bundle()` verifies an archive without extracting files to disk.

It rejects:

- malformed ZIPs;
- path traversal / absolute paths / backslash paths;
- duplicate ZIP members;
- directory members;
- missing `manifest.json`;
- oversized manifest/artifact/archive payloads;
- duplicate JSON keys;
- unknown manifest fields or unsupported versions;
- malformed artifact records;
- missing artifacts;
- unmanifested extra artifacts;
- size mismatches;
- SHA-256 mismatches.

Safety limits:

- maximum 512 evidence artifacts;
- maximum 1 MiB manifest;
- maximum 1 GiB per artifact;
- maximum 4 GiB total uncompressed payload.

## DPO4000 Desk integration

A18 extends the existing Recipe page rather than adding another navigation page.

After any A15 run result is available, the A18 panel offers:

- Scope PNG on/off;
- Waveforms on/off;
- Full / 1k / 10k / 100k / 1M waveform transfer selection;
- Save Evidence;
- cooperative Cancel Evidence;
- output size, artifact count, elapsed time, and bundle SHA-256 prefix.

Scope capture, waveform transfer, hashing, compression, and disk writes all execute through the existing serialized `_run_action(..., retain_session=True)` worker path. The Qt event loop only receives the final completion/error callback.

Cancellation is cooperative. A transfer already inside a VISA/driver call is not killed from another thread; the normal driver timeout remains the bound. Cancellation is checked between capture stages and throughout bundle creation, and no partial destination is finalized.

## Performance qualification

`scripts/benchmark_a18_evidence.py` covers 1k / 10k / 100k / 1M synthetic waveform cases and records:

- bundle creation min/p50/p95/p99/max;
- verification min/p50/p95/p99/max;
- atomic finalize latency;
- bundle size;
- samples/second.

Shared-hosted timings are smoke evidence only. Authoritative R0-T comparisons belong on the controlled performance runner.

## Hardware qualification

`tests/hardware/test_a18_evidence_hardware.py` contains:

1. a read-only DPO4054 case: A15 holdoff recipe → A16 PASS → CH1 1k waveform → `.dpoe` → full verification;
2. a reversible hardcopy case, gated by `DPO4000_ENABLE_WRITE_TESTS=1`, that captures the real scope PNG and verifies it is manifest-covered.

No hardware result is claimed until the self-hosted `dpo4000` runner actually executes these tests.
