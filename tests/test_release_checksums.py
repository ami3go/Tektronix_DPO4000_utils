from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from scripts.generate_release_checksums import generate_manifest, manifest_lines, release_files


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_release_files_are_sorted_by_relative_posix_path(tmp_path: Path) -> None:
    (tmp_path / "z.bin").write_bytes(b"z")
    (tmp_path / "nested").mkdir()
    (tmp_path / "nested" / "a.bin").write_bytes(b"a")
    output = tmp_path / "SHA256SUMS"
    output.write_text("stale\n", encoding="utf-8")

    files = release_files(tmp_path, output=output)

    assert [path.relative_to(tmp_path).as_posix() for path in files] == [
        "nested/a.bin",
        "z.bin",
    ]


def test_manifest_lines_are_sha256sum_compatible_and_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "A file.zip"
    second = tmp_path / "linux.bin"
    first.write_bytes(b"windows")
    second.write_bytes(b"linux")

    files = release_files(tmp_path)
    lines = manifest_lines(tmp_path, files)

    assert lines == (
        f"{_digest(b'windows')}  A file.zip",
        f"{_digest(b'linux')}  linux.bin",
    )


def test_generate_manifest_excludes_itself_and_is_reproducible(tmp_path: Path) -> None:
    assets = tmp_path / "release-assets"
    assets.mkdir()
    (assets / "one.bin").write_bytes(b"one")
    (assets / "two.bin").write_bytes(b"two")
    output = assets / "SHA256SUMS"

    generate_manifest(assets, output)
    first = output.read_text(encoding="utf-8")
    generate_manifest(assets, output)
    second = output.read_text(encoding="utf-8")

    assert first == second
    assert "SHA256SUMS" not in first
    assert first.splitlines() == [
        f"{_digest(b'one')}  one.bin",
        f"{_digest(b'two')}  two.bin",
    ]


def test_generate_manifest_rejects_empty_release_directory(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="No release files found"):
        generate_manifest(tmp_path, tmp_path / "SHA256SUMS")


def test_generate_manifest_requires_output_inside_release_directory(tmp_path: Path) -> None:
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "one.bin").write_bytes(b"one")

    with pytest.raises(ValueError, match="inside the release asset directory"):
        generate_manifest(assets, tmp_path / "SHA256SUMS")
