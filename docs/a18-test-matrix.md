# A18 Evidence Bundle Test Matrix

| Area | Required coverage |
|---|---|
| Minimal bundle | recipe result only; valid manifest closure |
| Full bundle | recipe + A16 result + PNG + waveform index/raw payload |
| Integrity | artifact size and SHA-256 verified; whole bundle SHA-256 stable |
| Recipe values | scalar, bytes summary, array/large-value bounded serialization |
| Waveform | exact raw bytes, source/label/range/preamble/sample type metadata |
| PNG | valid signature accepted; malformed image rejected before finalize |
| Atomic finalize | existing destination preserved until successful `os.replace()` |
| Cancellation | temporary archive removed; existing destination preserved |
| ZIP security | traversal, absolute/backslash paths, directories, duplicates rejected |
| Manifest security | duplicate JSON keys, unknown fields/version, malformed records rejected |
| Closure | missing manifest artifact and unmanifested extra ZIP member rejected |
| Corruption | changed artifact payload produces SHA-256 verification failure |
| Limits | artifact count, manifest size, artifact size, total uncompressed size |
| GUI boundary | public driver API only; no raw VISA/SCPI; bundle work inside worker callback |
| GUI controls | PNG/waveform toggles, Full/1k/10k/100k/1M selection, save/cancel/status |
| Scaling | synthetic 1k/10k/100k/1M creation + verification timings |
| Hardware | read-only CH1 1k waveform bundle; reversible real PNG bundle |

## Regression gate

Before A18 is qualified:

1. Python 3.10, 3.11, 3.12, and 3.13 `pytest -q` pass.
2. Ruff passes.
3. Full PySide6 offscreen regression passes.
4. Linux and Windows packaged DPO4000 Desk startup checks pass.
5. 1k/10k/100k/1M A18 benchmark smoke completes and every generated archive verifies.
6. DPO4054 read-only waveform qualification passes.
7. Reversible real-screen qualification passes when write/reversible tests are enabled.
8. Controlled-runner R0-T captures evidence completion, hash/manifest, waveform scaling, finalize, cancellation cleanup, and GUI heartbeat timing.
