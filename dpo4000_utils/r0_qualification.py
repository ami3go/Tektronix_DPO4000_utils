"""Fail-closed, setup-restoring context for physical R0 qualification.

The original *LRN?/SET? snapshot is durable before any intentional write.
Restoration is always attempted and checked; failure blocks baseline publication.
No REF waveform contents are preserved by a setup string.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from .settings import build_scope_settings_payload, restore_setup_verified


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    data = (json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    temp: Path | None = None
    try:
        with NamedTemporaryFile(mode="wb", dir=path.parent, prefix=f".{path.name}.",
                                suffix=".tmp", delete=False) as stream:
            temp = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


class VerifiedSetupGuard:
    """Require an exact expected IDN and verify initial/final setup equivalence.

    The caller owns the scope connection. The guard reconnects after a test
    disconnect if necessary, then restores and verifies the original setup.
    If restoration fails, it raises even when benchmark collection succeeded.
    """

    def __init__(
        self,
        capture: Any,
        output_dir: Path,
        expected_idn: str,
        *,
        settle_timeout_s: float = 10.0,
        poll_interval_s: float = 0.5,
    ):
        if not expected_idn.strip():
            raise ValueError("An operator-verified exact --expected-idn is mandatory")
        self.settle_timeout_s = settle_timeout_s
        self.poll_interval_s = poll_interval_s
        self.capture = capture
        self.output_dir = Path(output_dir)
        self.expected_idn = expected_idn.strip()
        self.initial: dict[str, Any] | None = None
        self.report: dict[str, Any] = {"status": "NOT_RUN", "verified": False}

    def __enter__(self) -> "VerifiedSetupGuard":
        scope = self.capture._require_scope()
        idn = scope.query_identity().strip()
        if idn != self.expected_idn:
            raise RuntimeError(f"Preflight identity mismatch: {idn!r} != expected IDN")
        initial = build_scope_settings_payload(scope.ensure_connected())
        if initial["instrument"].strip() != idn:
            raise RuntimeError("Instrument identity changed during setup capture")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.output_dir / "r0_initial_setup.json"
        # Exclusive publication prevents silently replacing the recovery setup.
        with path.open("x", encoding="utf-8") as stream:
            json.dump(initial, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        self.initial = initial
        self.report = {
            "status": "PENDING", "verified": False,
            "expected_idn": idn,
            "initial_setup_sha256": _sha256(initial["setup"]),
            "initial_setup_file": path.name,
        }
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        if self.initial is None:
            return False
        failure: Exception | None = None
        try:
            if self.capture.scope is None:
                self.capture.connect()
            scope = self.capture._require_scope()
            before_restore_idn = scope.query_identity().strip()
            if before_restore_idn != self.expected_idn:
                raise RuntimeError("Instrument identity changed; refusing to apply another unit's setup")
            instrument = scope.ensure_connected()
            # The scope settles asynchronously (cursor positions read back as defaults for a
            # few seconds after a record-length change): wait for the read-back instead of
            # judging the restoration 0.5 s after the write. Anything still different after
            # the settle window is a real failure and stays fail-closed below.
            _exact, passes, final_setup = restore_setup_verified(
                instrument, self.initial["setup"], check_error=True, restore_delay_s=0.5,
                always_apply=True, settle_timeout_s=self.settle_timeout_s,
                poll_interval_s=self.poll_interval_s,
            )
            self.report["restore_passes"] = passes
            final_idn = scope.query_identity().strip()
            self.report["final_idn"] = final_idn
            self.report["final_setup_sha256"] = _sha256(final_setup)
            if final_idn != self.expected_idn:
                raise RuntimeError("Instrument identity changed after restoration")
            if final_setup != self.initial["setup"]:
                raise RuntimeError("Final *LRN?/SET? setup does not match original snapshot")
            self.report.update(status="VERIFIED", verified=True)
        except Exception as restore_exc:
            failure = restore_exc
            self.report.update(status="RESTORATION_FAILED", verified=False,
                               error=f"{type(restore_exc).__name__}: {restore_exc}")
        finally:
            self.report["checked_at"] = datetime.now(timezone.utc).isoformat()
            _write_atomic(self.output_dir / "r0_setup_restoration.json", self.report)
        if failure is not None:
            raise RuntimeError(
                "R0 instrument restoration is NOT verified. Stop qualification and "
                "have the bench owner recover from r0_initial_setup.json."
            ) from failure
        return False
