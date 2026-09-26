# A16 Pass/Fail Rule Engine

Status: **implementation in progress on `a16-pass-fail-rules`**

A16 is the deterministic decision layer after A15 Test Recipe / Sequencer. It evaluates numeric measurements, recipe step results, and calculated scalar values without owning instrument I/O or control flow.

## Scope

A16 owns:

- GUI-independent numeric rule evaluation;
- `PASS`, `FAIL`, and `INVALID` outcomes;
- scalar comparison operators;
- inclusive range checks;
- absolute and relative delta checks;
- nested `AND`, `OR`, and `NOT` rule trees;
- stable rule IDs, timestamps, actual values, expected limits, and reasons;
- versioned JSON load/save;
- extraction of completed A15 step values into a rule input context;
- DPO4000 Desk rule editing and result presentation.

A16 does **not** own:

- VISA sessions or SCPI;
- Python expressions, `eval`, imports, or shell execution;
- recipe sequencing, loops, delays, retries, or branching;
- evidence packaging/report bundles (A18).

## Outcome semantics

Leaf rules return:

- `PASS` when the numeric condition is satisfied;
- `FAIL` when a valid finite numeric value violates the condition;
- `INVALID` when the input is missing, non-numeric, NaN/Inf, or the rule cannot be evaluated safely.

Invalid/unavailable values never become `PASS`.

Logical groups use deterministic three-state semantics:

- `AND`: `FAIL` if any child fails; otherwise `INVALID` if any child is invalid; otherwise `PASS`.
- `OR`: `PASS` if any child passes; otherwise `INVALID` if any child is invalid; otherwise `FAIL`.
- `NOT`: invert `PASS`/`FAIL`; preserve `INVALID`.

This makes a definite failure dominant in an `AND`, while a definite success is dominant in an `OR`.

## JSON schema v1

Top level:

```json
{
  "version": 1,
  "name": "5 V rail",
  "root": { "...": "rule node" }
}
```

Scalar comparison node:

```json
{
  "type": "compare",
  "id": "vout_min",
  "input": "MEAS1",
  "operator": ">=",
  "value": 4.95
}
```

Group node:

```json
{
  "type": "group",
  "id": "vout_window",
  "logic": "AND",
  "children": [
    {
      "type": "compare",
      "id": "vout_min",
      "input": "MEAS1",
      "operator": ">=",
      "value": 4.95
    },
    {
      "type": "compare",
      "id": "vout_max",
      "input": "MEAS1",
      "operator": "<=",
      "value": 5.05
    }
  ]
}
```

Supported scalar operators:

| Operator | Required fields | Semantics |
|---|---|---|
| `>` | `value` | actual > value |
| `>=` | `value` | actual >= value |
| `<` | `value` | actual < value |
| `<=` | `value` | actual <= value |
| `==` | `value` | exact numeric equality |
| `!=` | `value` | exact numeric inequality |
| `inside` | `low`, `high` | low <= actual <= high |
| `outside` | `low`, `high` | actual < low or actual > high |
| `abs_delta<=` | `reference`, `tolerance` | abs(actual-reference) <= tolerance |
| `rel_delta<=` | `reference`, `tolerance` | abs(actual-reference)/abs(reference) <= tolerance |

For `rel_delta<=`, a zero reference is `INVALID` rather than risking division by zero or silently changing semantics. Relative tolerance is a ratio (`0.01` = 1%).

## A15 recipe integration

`recipe_result_values()` converts completed `StepResult.value` fields into rule inputs:

- `step.<index>` — always available;
- `step.<step name>` — always available;
- `<step name>` — available only when the step name is unique;
- dataclass/mapping results are recursively flattened with dot-separated field names.

Example: a step named `MEAS1` returning `5.001` can be consumed directly by an A16 rule with `"input": "MEAS1"`.

Duplicate step names are deliberately not exposed as ambiguous direct names; use `step.<index>` instead.

## Safety / limits

- Maximum rule nodes: 10,000.
- Maximum rule-tree depth: 64.
- Rule IDs must be unique within a rule set.
- Unknown fields and future schema versions are rejected.
- All rule constants must be finite numbers.
- No expression language is accepted.

## DPO4000 Desk

The existing Recipe page gains:

- Load Rules;
- Save Rules;
- Validate Rules;
- rule JSON editor;
- rule result table with Rule / Status / Actual / Expected / Reason;
- final recipe status annotated with `PASS`, `FAIL`, or `INVALID` when a rule set is active.

Rule evaluation occurs after a completed recipe and does not touch the instrument worker/session.

## Definition of done

A16 is software-complete when:

- all scalar operators pass exact-boundary and epsilon-outside tests;
- NaN/Inf/missing/non-numeric values are `INVALID` and never `PASS`;
- AND/OR/NOT truth tables are covered;
- JSON round-trip and unknown-field/version rejection pass;
- A15 result extraction handles named/indexed/dataclass values deterministically;
- the Desk page exposes validation/result controls without raw transport access;
- Python 3.10–3.13, Ruff, full PySide6, and packaged Desk startup checks pass;
- a read-only DPO4054 A15→A16 integration test is available for the self-hosted runner.
