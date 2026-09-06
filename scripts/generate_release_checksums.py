#!/usr/bin/env python3
"""Generate a deterministic SHA-256 manifest for release assets."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Iterable

DEFAULT_OUTPUT_NAME = "SHA256SUMS"


def _sha256(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def release_files(root: Path, *, output: Path | None = None) -> tuple[Path, ...]:
    """Return regular release files in stable relative-path order."""
    root = root.resolve()
    output_resolved = output.resolve() if output is not None else None
    files = [
        path
        for path in root.rglob("*")
        if path.is_file() and (output_resolved is None or path.resolve() != output_resolved)
    ]
    return tuple(sorted(files, key=lambda path: path.relative_to(root).as_posix()))


def manifest_lines(root: Path, files: Iterable[Path]) -> tuple[str, ...]:
    """Return GNU-sha256sum-compatible lines using paths relative to *root*."""
    root = root.resolve()
    return tuple(
        f"{_sha256(path)}  {path.resolve().relative_to(root).as_posix()}"
        for path in files
    )


def generate_manifest(root: Path, output: Path) -> Path:
    """Write and return a deterministic SHA256SUMS-style manifest."""
    root = root.resolve()
    output = output.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Release asset directory does not exist: {root}")
    try:
        output.relative_to(root)
    except ValueError as exc:
        raise ValueError("Checksum manifest must be written inside the release asset directory.") from exc

    files = release_files(root, output=output)
    if not files:
        raise ValueError(f"No release files found under {root}")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(manifest_lines(root, files)) + "\n", encoding="utf-8")
    return output


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Directory containing final release assets")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=f"Manifest path (default: <root>/{DEFAULT_OUTPUT_NAME})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root
    output = args.output if args.output is not None else root / DEFAULT_OUTPUT_NAME
    generated = generate_manifest(root, output)
    print(generated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
