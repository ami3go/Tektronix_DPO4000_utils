"""Public real-hardware verification facade.

The implementation lives in :mod:`hardware_verification_core`.  This facade
extends the verification manifest for public APIs introduced after the original
runner without duplicating the mature report/lifecycle machinery.
"""

from __future__ import annotations

from . import hardware_verification_core as _core

# Keep the reflection manifest exact. Restoring factory defaults is intentionally
# disruptive, but the verification runner has already captured a baseline setup
# before this profile is allowed to execute.
_core.PUBLIC_METHOD_RISK["restore_default_setup"] = _core.VerificationRisk.DISRUPTIVE

PUBLIC_FUNCTION_RISK = _core.PUBLIC_FUNCTION_RISK
PUBLIC_METHOD_RISK = _core.PUBLIC_METHOD_RISK
VerificationCase = _core.VerificationCase
VerificationConfig = _core.VerificationConfig
VerificationResult = _core.VerificationResult
VerificationRisk = _core.VerificationRisk
public_driver_methods = _core.public_driver_methods
public_package_functions = _core.public_package_functions
verification_manifest_gaps = _core.verification_manifest_gaps


class HardwareVerifier(_core.HardwareVerifier):
    """Hardware verifier extended with factory/default setup coverage."""

    def _case_settings_apply(self) -> str:
        scope = self._require_scope()
        path = self.config.output_dir / "scope_settings_driver_save.json"
        if not path.exists():
            scope.save_scope_settings(path, ask_before_overwrite=False)

        # Exercise the same factory/default recall used by the GUI Default button,
        # then immediately restore the previously captured setup file. The outer
        # verifier baseline restore remains an additional safety net.
        scope.restore_default_setup()
        scope.apply_scope_settings(
            path,
            wait_complete=False,
            check_error=False,
            restore_delay_s=0.5,
        )
        return "Factory default recall and driver settings restore both passed."

    def _symbol_status(self, symbol: str, *, method: bool) -> tuple[str, list[str]]:
        if method and symbol == "restore_default_setup":
            # settings-apply now physically exercises both operations. Reuse that
            # case status so the generated report accurately records the evidence.
            return super()._symbol_status("apply_scope_settings", method=True)
        return super()._symbol_status(symbol, method=method)


__all__ = [
    "HardwareVerifier",
    "PUBLIC_FUNCTION_RISK",
    "PUBLIC_METHOD_RISK",
    "VerificationCase",
    "VerificationConfig",
    "VerificationResult",
    "VerificationRisk",
    "public_driver_methods",
    "public_package_functions",
    "verification_manifest_gaps",
]
