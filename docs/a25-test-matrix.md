# A25 Headless Job Runner Test Matrix

| Area | Required cases |
|---|---|
| JSON input | valid object, malformed JSON, duplicate keys, wrong top-level type, oversized file |
| Validation-only | valid recipe/rules, unknown method, invalid config mapping, zero session opens |
| Session lifecycle | open once, close on success, close on IDN mismatch, close on recipe failure |
| Recipe result | completed -> 0, failed -> 4, cancelled -> 130 |
| Rule result | PASS -> 0, FAIL -> 5, INVALID -> 6 |
| Runtime | identity mismatch / session error -> 3 |
| Scientific export | optional DPOZ/NPZ output, metadata, round-trip, export failure -> 7 |
| Reporting | stable schema, atomic replace, dataclass/enum/path/timestamp serialization |
| Cancellation | cancel before session, cancel during Delay, first SIGINT cooperative cancellation |
| CLI | installed `dpo4000-job`, `--help`, `--validate-only`, environment resource fallback |
| Performance | startup, validation-only, direct-vs-headless overhead, large recipe scaling |
| HIL | read-only DPO4054 holdoff recipe + A16 rule + cleanup |

## Regression gate

Before A25 is ready to integrate:

1. Python 3.10–3.13 full accumulated tests pass.
2. Ruff passes.
3. Full PySide6 suite remains green even though A25 itself is headless.
4. Linux and Windows DPO4000 Desk package startup remains green.
5. `dpo4000-job --validate-only` succeeds without a VISA resource.
6. Synthetic direct-vs-headless benchmark passes for representative recipe sizes.
7. Cooperative cancellation and cleanup tests are bounded.
8. Read-only DPO4054 HIL runs on the self-hosted runner.
9. Controlled runner records process startup, first-I/O, p50/p95/p99, cancel, and shutdown latencies.
