"""Command-line inspection and streaming conversion for DPO4LOG files."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .dpo4log import Dpo4LogError, iter_dpo4log_records, scan_dpo4log
from .mixed_csv import MixedCsvStreamWriter


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dpo4000-log",
        description="Inspect or stream-convert DPO4000 Logger DPO4LOG files.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    inspect_parser = sub.add_parser("inspect", help="Inspect structure without loading records into RAM.")
    inspect_parser.add_argument("path", type=Path)
    inspect_parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")

    convert_parser = sub.add_parser("convert", help="Stream complete records into tagged CSV.")
    convert_parser.add_argument("path", type=Path)
    convert_parser.add_argument("--csv", required=True, type=Path, help="Destination CSV path (must not exist).")
    return parser


def _summary(path: Path):
    scan = scan_dpo4log(path)
    return scan, {
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "record_count": scan.record_count,
        "clean_end": scan.clean_end,
        "truncated_or_corrupt": scan.truncated,
        "error": scan.error,
        "header": dict(scan.header),
    }


def _inspect(path: Path, *, as_json: bool) -> int:
    scan, summary = _summary(path)
    if as_json:
        print(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False))
    else:
        print(f"DPO4LOG: {path}")
        print(f"Size: {summary['size_bytes']} bytes")
        print(f"Records: {scan.record_count}")
        print(f"Clean END: {'yes' if scan.clean_end else 'no'}")
        print(f"Truncated/corrupt: {'yes' if scan.truncated else 'no'}")
        if scan.error:
            print(f"Error: {scan.error}")
        if scan.header:
            print("Header:")
            print(json.dumps(dict(scan.header), indent=2, sort_keys=True, allow_nan=False))
    return 0 if scan.clean_end and not scan.truncated else 2


def _convert(path: Path, csv_path: Path) -> int:
    scan = scan_dpo4log(path)
    converted = 0
    writer = MixedCsvStreamWriter(csv_path)
    try:
        for record in iter_dpo4log_records(path, strict=False):
            writer.append(record)
            converted += 1
    finally:
        writer.close()
    print(f"Converted {converted} complete records to {csv_path}")
    if converted != scan.record_count:
        print(
            f"warning: inspection found {scan.record_count} complete record frames but "
            f"converter emitted {converted}",
            file=sys.stderr,
        )
        return 2
    if not scan.clean_end or scan.truncated:
        detail = scan.error or "source log has no clean END frame"
        print(f"warning: {detail}; complete records were recovered", file=sys.stderr)
        return 2
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "inspect":
            return _inspect(args.path, as_json=bool(args.json))
        if args.command == "convert":
            return _convert(args.path, args.csv)
    except (OSError, Dpo4LogError, ValueError) as exc:
        print(f"dpo4000-log: {exc}", file=sys.stderr)
        return 1
    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
