# A25 Headless Job Runner

Status: **A25 baseline on `main`; headless safety hardening pending draft PR verification**

A25 exposes the existing A15/A16/A21 stack as a non-Qt command-line job runner suitable for Linux, CI, lab automation, and unattended execution.

## Command

```bash
dpo4000-job \
  --resource 'TCPIP0::192.168.0.5::INSTR' \
  --recipe recipe.json \
  --rules rules.json \
  --report result.json
```

The command is installed by `python -m pip install -e .[dev]`, without PySide6.
No GUI or Qt application is created. A25 disallows the A15 setup-file replay method\n(which could submit user-authored raw SCPI) and direct local-file-writing recipe\nmethods. Use typed driver commands and controlled A21 export/report outputs.

Precedence for each supported environment setting is **CLI > environment > default**:

| CLI flag | Environment variable | Default |
|---|---|---|
| `--resource` | `DPO4000_RESOURCE` | none (mandatory for execution) |
| `--expect-idn` | `DPO4000_EXPECT_IDN` | none |
| `--timeout-ms` | `DPO4000_TIMEOUT_MS` | 20000 ms |

An explicitly supplied CLI value overrides a malformed environment value.
Malformed `DPO4000_TIMEOUT_MS` is a validation error (exit 2) when used.
The allowed timeout range is 1..600000 ms.

Validation without VISA:

```bash
dpo4000-job --recipe recipe.json --rules rules.json --validate-only
```

A25 performs the same A15 whole-recipe method/signature/config-dataclass preflight before opening a session. `--validate-only` therefore validates the job without connecting to an instrument.

## Reuse boundaries

A25 does not implement another automation engine.

It reuses:

- **A15** `RecipeSequencer` for execution, retry, Delay, and cancellation semantics;
- **A16** `RuleEngine` and `recipe_result_values()` for PASS/FAIL/INVALID;
- **A21** `export_scientific_dataset()` for optional waveform export;
- `scope_session()` for one short-lived driver-owned connection lifecycle.

A20 is unrelated to headless execution and is only the stacked development base. A18 is not required by A25.

## Input validation

Recipe and rule files:

- must be UTF-8 JSON objects;
- are limited to 10 MB each;
- reject duplicate JSON keys, invalid UTF-8 and nonstandard `NaN`/`Infinity` literals;
- bound bytes read (including files changed concurrently) rather than relying on `stat()`;
- reject report/export paths that overlap input files or each other;
- use the existing A15/A16 versioned schemas;
- are fully loaded and preflighted before instrument I/O.

The runner refuses an execution job without a VISA resource. `--validate-only` is the only mode where a resource is optional.

Output file collisions and invalid or incomplete export options are rejected
before the first VISA session opens. No `eval`, arbitrary private methods,
raw SCPI, shell execution or dynamic imports are exposed by A25.

## Exit codes

| Code | Meaning |
|---:|---|
| 0 | completed / PASS / validation succeeded |
| 2 | job/recipe/rule validation error |
| 3 | runtime/session/identity error |
| 4 | A15 recipe failed |
| 5 | A16 rule result `FAIL` |
| 6 | A16 rule result `INVALID` |
| 7 | requested A21 export failed |
| 130 | cancelled / Ctrl-C |

Machine report status vocabulary: `pass`, `completed` (recipe without rules),
`validated` (validation-only), `validation_error`, `runtime_error`,
`recipe_failed`, `rule_failed`, `rule_invalid`, `export_error`, `cancelled`.
A16's `PASS`/`FAIL`/`INVALID` decision is separately captured in `rule_result.status`.

The classification separates DUT limit failures from infrastructure errors.
An explicit report-write failure returns code 3 even if evaluation previously
succeeded or failed; it does not leave a partially replaced destination.

## Identity gate

`--expect-idn TEXT` requires the connected scope's `*IDN?` response to contain `TEXT` case-insensitively before the recipe starts.

Example:

```bash
dpo4000-job \
  --resource 'TCPIP0::192.168.0.5::INSTR' \
  --expect-idn 'TEKTRONIX,DPO4054' \
  --recipe recipe.json
```

A25 additionally rejects all non-Tektronix or non-DPO4000/MSO4000-family\nidentities before the first recipe step, even without `--expect-idn`.\n`--expect-idn` can enforce an exact bench model substring such as DPO4054.\nAn identity mismatch exits with code 3 and still closes the session.

## Scientific export

Optional A21 export after a completed recipe:

```bash
dpo4000-job \
  --resource 'TCPIP0::192.168.0.5::INSTR' \
  --recipe recipe.json \
  --export waveforms.dpoz \
  --export-points 100000
```

Options:

- `--export PATH`
- `--export-format npz|dpoz` (otherwise inferred from suffix)
- `--export-points N`
- `--export-compressed`

Any format, point count, or compression option without `--export` is rejected.
Unsupported output extensions without `--export-format` are rejected before VISA.
Scientific export errors use code 7; A21 owns the serializer and atomic data output.
An export error after rule evaluation takes precedence over the rule outcome
because the requested job output is incomplete.

The export metadata includes scope identity, recipe name, and A16 result when rules are active.

## Result report

`--report PATH` writes a JSON report atomically using a same-directory temporary file, `fsync`, and `os.replace()`.

Report schema identifier:

```text
dpo4000-headless-job
```

Schema version: `1` (keys `version` and backwards-compatible `schema_version`).

The output uses a same-directory temporary file, flush, `fsync`,
and atomic `os.replace`, cleaning the temporary file when replacement fails.
Numerically non-finite step values are serialized as strings, never invalid
JSON `NaN`/`Infinity` tokens.

The report includes:

- exit code / status / message;
- UTC start/finish timestamps and total duration;
- VISA resource and IDN;
- recipe name and A15 step results;
- optional A16 decision tree;
- optional A21 export result;
- whether the run was validation-only.

## Ctrl-C / cancellation

First `SIGINT` requests cooperative cancellation through the active `RecipeSequencer`.

- Delay and retry waits react at A15's cancellation checkpoint cadence.
- Between driver calls, cancellation is immediate at the next checkpoint.
- A VISA call already executing is **not** killed from another thread; the configured driver/VISA timeout remains its upper bound.

A second `SIGINT` raises `KeyboardInterrupt` so an operator can force termination if the backend itself is stuck outside the expected timeout contract.

Cancellation exits with code 130. Session cleanup still runs through `scope_session()`.
Cancelling while a driver operation is active prevents later recipe calls after
that operation returns. A given `HeadlessJobRunner` permits only one active
job; a simultaneous `run()` returns code 3 without opening a second session.
A cancelled runner instance remains cancelled: construct a new instance to
start a fresh job.

## Performance qualification

`scripts/benchmark_a25_job_runner.py` compares:

- validation-only duration;
- complete headless job duration;
- direct A15 sequencer duration;
- headless orchestration overhead;
- steps/second;
- median/p95 validation, total fake-job, direct A15, and atomic report-write latency.

Run `python scripts/benchmark_a25_job_runner.py --steps 1,100,1000 --repetitions 5 --output a25-benchmark.json`.
Numbers from hosted CI are smoke measurements, not physical instrument timing.

Shared-runner numbers are smoke evidence only. Controlled qualification must additionally measure the regression-plan requirements:

- process startup latency;
- validation-only latency;
- first instrument-operation latency;
- total recipe overhead versus direct sequencing;
- Ctrl-C/cancel latency;
- session cleanup/shutdown latency;
- p50/p95/p99 distributions.

## Hardware qualification

The focused DPO4054 test is read-only:

1. open one headless `scope_session`;
2. verify expected DPO4054 identity;
3. run an A15 `get_trigger_holdoff` recipe;
4. evaluate an A16 `HOLDOFF >= 0` rule;
5. require exit code 0 / status `pass`;
6. close the session.

No trigger/acquisition configuration write permission is required.
A dedicated opt-in workflow `.github/workflows/a25-headless-hil.yml`
runs on `[self-hosted, dpo4000]`, uses an installed CLI, validates the report,
runs the API test, performs a subsequent read-only identity query to prove
release of the session, and uploads benchmark/report/JUnit artifacts.
**Hardware qualification is PENDING until that workflow actually runs successfully.**

## Unattended systemd example

Use an account with appropriately restricted VISA and output-path permissions.
The scope configuration is not changed by the service itself; recipe calls may
change instrument state, so use only reviewed recipes.

```ini
[Unit]
Description=DPO4000 read-only test
After=network-online.target

[Service]
Type=oneshot
Environment=DPO4000_RESOURCE=TCPIP0::192.168.0.5::INSTR
Environment=DPO4000_EXPECT_IDN=TEKTRONIX,DPO4054
ExecStart=/opt/dpo4000-venv/bin/dpo4000-job --recipe /opt/jobs/holdoff.json --rules /opt/jobs/holdoff-rules.json --report /var/lib/dpo4000/last-run.json
```

For CI/Robot Framework, classify the process exit code rather than parsing stdout.
A read-only validation preflight can run before physical HIL without VISA access.

## Definition of done

A25 software is complete when:

- validation-only performs zero instrument I/O;
- malformed later recipe steps fail before the first session operation;
- exit codes distinguish validation/runtime/recipe/rule/export/cancel outcomes;
- session cleanup occurs on success and failure;
- Ctrl-C/cancel reaches A15 cooperative cancellation;
- JSON result reporting is atomic;
- optional A21 export round-trips;
- the installed `dpo4000-job` entry point validates a recipe without VISA;
- full accumulated Python/Ruff/PySide6/package regression remains green;
- read-only DPO4054 HIL is available for self-hosted qualification.

## Human-readable output and integrations

`--output-format text` prints a concise summary instead of the JSON result on stdout (JSON remains the default, and `--report` is always JSON):

```text
dpo4000-job: RULE FAILED (exit 5) in 1.204 s
Recipe: Probe Comp acceptance
Scope: TEKTRONIX,DPO4054,C000000,CF:91.1CT FV:v2.68
Steps: completed, 4 steps, 1.180 s
Rules: acceptance FAIL (1 FAIL, 2 PASS)
  FAIL vpp_min: actual 0.94 — condition not satisfied
Message: A16 rule set evaluated to FAIL
```

Integration examples using the CLI as the boundary:

- `examples/robot_framework/` — Robot Framework suite (offline validation case runs without hardware; the hardware case is tagged `hardware` and skipped unless `DPO4000_RESOURCE` is set).
- `examples/opentap/` — OpenTAP Python test step mapping exit codes to verdicts (untested; OpenTAP is not in CI).
