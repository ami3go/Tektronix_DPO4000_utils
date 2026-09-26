# A21 Scientific Export Test Matrix

| Area | Required cases |
|---|---|
| format normalization | `npz`, `.npz`, NumPy alias, `dpoz`, ZIP alias, invalid extension |
| dataset validation | empty dataset, duplicate source, bad range/count, non-finite metadata/raw float, unsupported raw type |
| NPZ export | raw/X/Y arrays, UTF-8 manifest, compressed/uncompressed, metrics |
| NPZ import | `allow_pickle=False`, manifest required, dtype/shape/count validation, exact round-trip |
| DPOZ export | manifest, raw member, CSV member, little-endian raw, compressed/uncompressed |
| DPOZ import | ZIP validity, deterministic member names, raw byte-size check, exact round-trip |
| atomicity | failed write removes temporary file and preserves existing destination |
| schema | version, schema id, unknown fields, malformed preamble/timestamp/metadata |
| safety | trace limit, total-sample limit, manifest-size limit, duplicate trace indices |
| scaling smoke | 1k / 10k / 100k / 1M synthetic records |
| throughput | samples/s and MB/s for export; samples/s for import |
| memory | traced peak Python bytes during export/import |
| GUI contract | File page preserved, A21 panel attached, no raw VISA/SCPI, worker action used |
| GUI responsiveness | controlled runner heartbeat during 1M export |
| HIL | DPO4054 1k CH1 -> NPZ/DPOZ -> exact import round-trip |
| packaging | Linux/Windows Desk startup with NumPy scientific dependency included |

## Functional regression gate

Before A21 is ready to merge:

1. full existing pytest suite passes on Python 3.10, 3.11, 3.12, and 3.13;
2. Ruff passes;
3. full PySide6 offscreen suite passes;
4. benchmark smoke (1k/10k/100k for both formats) produces valid JSON and exact round trips;
5. Linux and Windows packaged DPO4000 Desk startup checks pass;
6. self-hosted DPO4054 A21 qualification passes when the `dpo4000` runner is available.

## Controlled performance gate

The authoritative A21 performance runner should retain per-format samples for 1k, 10k, 100k, 1M, and the largest qualified DPO4054 record size. Record at least p50/p95/p99/max across repeated runs for:

- export duration;
- import duration;
- samples/s;
- MB/s;
- peak memory;
- GUI heartbeat p50/p95/p99/max stall.

Use the relative-plus-absolute regression policy from `docs/regression-test-plan.md`; do not regenerate the baseline merely to accept a slowdown.
