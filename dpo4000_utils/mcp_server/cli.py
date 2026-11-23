"""Headless stdio MCP server entry point.

No VISA resource is opened at startup. Real instrument I/O always requires
both an explicit resource name and an explicit enable flag. HTTP transport is
intentionally not shipped until authentication and cross-process ownership
coordination are implemented.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

from .gateway import ReadOnlyGateway
from .protocol import build_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dpo4000-mcp",
        description="Opt-in, stdio-only, read-only Tektronix DPO4000 MCP server",
    )
    parser.add_argument(
        "--resource",
        default=None,
        help="Explicit VISA resource name (no discovery or connection at startup)",
    )
    parser.add_argument(
        "--allow-instrument-io",
        action="store_true",
        help="Enable read-only instrument I/O (requires exclusive operator-controlled bench)",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=20_000,
        help="PyVISA request timeout in milliseconds (1..600000)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.allow_instrument_io and args.resource is None:
        parser.error("--allow-instrument-io requires --resource")
    if not 1 <= args.timeout_ms <= 600_000:
        parser.error("--timeout-ms must be between 1 and 600000")
    gateway = ReadOnlyGateway(
        resource=args.resource,
        allow_instrument_io=args.allow_instrument_io,
        timeout_ms=args.timeout_ms,
    )
    try:
        server = build_server(gateway)
        server.run(transport="stdio")
    finally:
        gateway.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
