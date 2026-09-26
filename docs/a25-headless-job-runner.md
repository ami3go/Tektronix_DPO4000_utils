# A25 Headless Job Runner

Status: implementation on `a25-headless-job-runner`.

A25 exposes the existing A15/A16/A21 stack as a non-Qt command-line job runner suitable for Linux, CI, lab automation, and unattended execution.

## Command

```bash
dpo4000-job \
  --resource 'TCPIP0::192.168.0.5::INSTR' \
  --recipe recipe.json \
  --rules rules.json \
  --report result.json
```

`DPO4000_RESOURCE` may supply the resource when `--resource` is omitted.

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
- reject duplicate JSON keys;
- use the existing A15/A16 versioned schemas;
- are fully loaded and preflighted before instrument I/O.

The runner refuses an execution job without a VISA resource. `--validate-only` is the only mode where a resource is optional.

Timeout range: 1..600000 ms.

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

This separation is intended for shell scripts and CI systems that must distinguish DUT failure from an infrastructure/validation error.

## Identity gate

`--expect-idn TEXT` requires the connected scope's `*IDN?` response to contain `TEXT` case-insensitively before the recipe starts.

Example:

```bash
dpo4000-job \
  --resource 'TCPIP0::192.168.0.5::INSTR' \
  --expect-idn 'TEKTRONIX,DPO4054' \
  --recipe recipe.json
```

An identity mismatch exits with code 3 and still closes the session.

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

The export metadata includes scope identity, recipe name, and A16 result when rules are active.

## Result report

`--report PATH` writes a JSON report atomically using a same-directory temporary file, `fsync`, and `os.replace()`.

Report schema identifier:

```text
dpo4000-headless-job
```

Schema version: `1`.

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

## Performance qualification

`scripts/benchmark_a25_job_runner.py` compares:

- validation-only duration;
- complete headless job duration;
- direct A15 sequencer duration;
- headless orchestration overhead;
- steps/second.

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
