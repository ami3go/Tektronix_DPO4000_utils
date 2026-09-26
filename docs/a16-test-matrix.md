# A16 Pass/Fail Rule Engine Test Matrix

| Area | Required cases |
|---|---|
| `>` / `>=` / `<` / `<=` | pass, fail, exact boundary |
| `==` / `!=` | exact equality and epsilon difference |
| `inside` | low boundary, high boundary, inside, below, above |
| `outside` | low/high boundaries fail, epsilon outside passes |
| absolute delta | exact tolerance boundary and epsilon outside |
| relative delta | exact tolerance boundary, epsilon outside, zero reference -> INVALID |
| invalid inputs | missing, `None`, bool, string, NaN, +Inf, -Inf -> INVALID |
| AND | all pass, one fail, invalid-only uncertainty, fail+invalid |
| OR | one pass, all fail, invalid-only uncertainty, fail+invalid |
| NOT | PASS->FAIL, FAIL->PASS, INVALID->INVALID |
| schema | round-trip, unknown fields, future version, bad operator, bad logic |
| rule tree safety | duplicate IDs, empty group, NOT arity, max depth, max node count |
| recipe context | index key, unique name key, duplicate name handling, dataclass/mapping flattening |
| GUI contract | rule editor/buttons/table, no raw scope/VISA transport, evaluate only after completed recipe |
| packaging | Linux and Windows `--startup-check` |
| hardware | read-only DPO4054 recipe -> numeric value -> A16 decision |

## Regression gate

Before A16 is ready to stack on the next roadmap item:

1. `pytest -q` passes on Python 3.10, 3.11, 3.12, and 3.13.
2. `ruff check dpo4000_utils tests scripts tektronix_utils.py` passes.
3. Full PySide6 offscreen suite passes.
4. Linux and Windows packaged DPO4000 Desk startup checks pass.
5. The self-hosted DPO4054 test is queued/run when the `dpo4000` runner is available.
