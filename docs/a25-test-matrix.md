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

## Automated evidence paths

| Contract | Test / workflow |
|---|---|
| Strict UTF-8, duplicate keys, non-finite and deeply nested JSON, size cap | `tests/test_a25_job_runner_hardening.py` |
| A15 method/argument validation before I/O | `tests/test_a25_job_runner.py`, `tests/test_a25_job_runner_hardening.py` |
| Validation-only and no Qt import | `tests/test_a25_job_runner_hardening.py` |
| A16 PASS/FAIL/INVALID exit mapping | `tests/test_a25_job_runner.py` |
| One session, concurrent-job rejection, cancellation after blocking call | `tests/test_a25_job_runner_hardening.py` |
| SIGINT CLI and installed module CLI | `tests/test_a25_job_runner_cli.py`, `.github/workflows/tests.yml` |
| Report schema/version, Unicode/finite JSON, atomic rollback | `tests/test_a25_job_runner.py`, `tests/test_a25_job_runner_hardening.py` |
| A21 NPZ and DPOZ round trip, export failure classification | `tests/test_a25_job_runner.py`, `tests/test_a25_job_runner_errors.py` |
| Median/p95 fake A15 vs A25 and report write | `scripts/benchmark_a25_job_runner.py` |
| Hosted Python 3.10–3.13, Ruff, full Qt regression | `.github/workflows/tests.yml` |
| Linux and Windows packaged Desk startup | `.github/workflows/build-gui-executables.yml` |
| Real installed CLI + API read-only DPO4054 evidence | `.github/workflows/a25-headless-hil.yml` (opt-in, not yet qualified) |

The HIL workflow is manual and requires `[self-hosted, dpo4000]` plus a
verified VISA resource. A queued job or unexecuted workflow is **PENDING**,
not a physical PASS. Its initial recipe is only `get_trigger_holdoff`;
it does not qualify scope-writing recipes.

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
