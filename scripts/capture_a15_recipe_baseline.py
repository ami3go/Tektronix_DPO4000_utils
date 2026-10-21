#!/usr/bin/env python3
"""Capture A15 recipe/sequencer R0-T candidate metrics on a DPO4000 scope."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from dpo4000_utils.baseline_capture import build_baseline_header
from dpo4000_utils.connection import visaResourceAddr
from dpo4000_utils.instrument import DPO4054
from dpo4000_utils.recipe_baseline import capture_recipe_timing


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resource", default=visaResourceAddr)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-ms", type=int, default=20_000)
    parser.add_argument("--reps", type=int, default=20)
    parser.add_argument("--dispatch-steps", type=int, default=1_000)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scope = DPO4054(
        args.resource,
        auto_connect=False,
        timeout_ms=args.timeout_ms,
        read_termination="\n",
        write_termination="\n",
    )
    scope.connect()
    try:
        idn = scope.query_identity()
        payload = build_baseline_header(args.resource, idn)
        payload["a15_recipe"] = capture_recipe_timing(
            scope,
            reps=args.reps,
            dispatch_steps=args.dispatch_steps,
        )
    finally:
        scope.disconnect()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
