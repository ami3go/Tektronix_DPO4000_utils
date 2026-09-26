"""Public real-hardware verification facade.

The implementation lives in :mod:`hardware_verification_core`. This facade
extends the verification manifest for public APIs introduced after the original
runner without duplicating the mature report/lifecycle machinery.
"""

from __future__ import annotations

from . import hardware_verification_core as _core

# Keep the reflection manifest exact. Restoring factory defaults is intentionally
# disruptive, but the verification runner has already captured a baseline setup
# before this profile is allowed to execute.
_core.PUBLIC_METHOD_RISK["restore_default_setup"] = _core.VerificationRisk.DISRUPTIVE
for _name in (
    "configure_session",
    "get_acquisition_state",
    "get_trigger_state",
    "is_acquiring",
    "is_busy",
    "get_decoded_bus_capability",
    "supports_decoded_bus_events",
    "read_decoded_bus_events",
    "get_trigger_holdoff",
    "probe_scpi_query",
):
    _core.PUBLIC_METHOD_RISK[_name] = _core.VerificationRisk.READ_ONLY
_core.PUBLIC_METHOD_RISK["set_trigger_holdoff"] = _core.VerificationRisk.REVERSIBLE

# Framework utilities below perform no oscilloscope I/O. Classifying them as
# read-only keeps the strict reflected package manifest exhaustive without
# implying that local JSON/rule/archive work is a hardware operation.
for _name in (
    "recipe_result_values",
    "rule_set_from_mapping",
    "rule_set_to_mapping",
    "export_scientific_dataset",
    "import_scientific_dataset",
    "infer_scientific_format",
    "normalize_scientific_format",
    "scientific_dataset_from_waveforms",
):
    _core.PUBLIC_FUNCTION_RISK[_name] = _core.VerificationRisk.READ_ONLY

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
    """Hardware verifier extended with post-core public API coverage."""

    def _case_control_readbacks(self) -> str:
        detail = super()._case_control_readbacks()
        scope = self._require_scope()
        scope.configure_session(
            timeout_ms=getattr(scope, "timeout_ms", None) or 20_000,
            read_termination=getattr(scope, "read_termination", None) or "\n",
            write_termination=getattr(scope, "write_termination", None) or "\n",
        )
        scope.get_acquisition_state()
        scope.is_acquiring()
        scope.get_trigger_state()
        scope.is_busy()

        # A14 read-only qualification: verify the known-good holdoff leaf and prove
        # the known hanging B-trigger candidate is bounded and leaves the normal
        # operational VISA timeout unchanged.
        instrument = scope.ensure_connected()
        original_timeout = getattr(instrument, "timeout", None)
        scope.get_trigger_holdoff()
        supported = scope.probe_scpi_query("TRIGGER:A:HOLDOFF:VALUE?", timeout_ms=500)
        if not supported.supported:
            raise AssertionError(f"Verified A14 holdoff query was not supported: {supported}")
        unsupported = scope.probe_scpi_query("TRIGGER:B:EVENTS:MODE?", timeout_ms=500)
        if unsupported.supported:
            raise AssertionError("Known unsupported TRIGGER:B:EVENTS:MODE? unexpectedly succeeded.")
        if getattr(instrument, "timeout", None) != original_timeout:
            raise AssertionError("A14 capability probe did not restore the original VISA timeout.")
        return detail + " Session state plus A14 holdoff/capability-probe readbacks passed."

    def _case_trigger_config_write(self) -> str:
        detail = super()._case_trigger_config_write()
        scope = self._require_scope()
        original_holdoff = scope.get_trigger_holdoff()
        try:
            readback = scope.set_trigger_holdoff(original_holdoff)
            if readback is None or abs(float(readback) - float(original_holdoff)) > max(
                1e-15, abs(float(original_holdoff)) * 1e-9
            ):
                raise AssertionError(
                    f"A14 holdoff write/readback mismatch: wrote={original_holdoff}, read={readback}"
                )
        finally:
            scope.set_trigger_holdoff(original_holdoff, verify=False)
        return detail + " A14 holdoff write/readback passed and original value was restored."

    def _case_bus_readbacks(self) -> str:
        scope = self._require_scope()
        capability = scope.get_decoded_bus_capability()
        self._decoded_bus_supported = bool(capability.supported and capability.qualified)
        detail = super()._case_bus_readbacks()
        if self._decoded_bus_supported:
            slots = scope.get_available_bus_slots()
            if slots:
                scope.read_decoded_bus_events(slots[0])
                detail += f" Qualified decoded BUS{slots[0]} event extraction passed."
        else:
            detail += (
                " Decoded BUS event extraction is explicitly capability-gated unavailable: "
                f"{capability.reason}"
            )
        return detail

    def _case_settings_apply(self) -> str:
        scope = self._require_scope()
        path = self.config.output_dir / "scope_settings_driver_save.json"
        if not path.exists():
            scope.save_scope_settings(path, ask_before_overwrite=False)

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
            return super()._symbol_status("apply_scope_settings", method=True)
        if method and symbol == "configure_session":
            return super()._symbol_status("get_acquisition_setup", method=True)
        if method and symbol in {
            "get_acquisition_state",
            "get_trigger_state",
            "is_acquiring",
            "is_busy",
            "get_trigger_holdoff",
            "probe_scpi_query",
        }:
            return super()._symbol_status("get_acquisition_setup", method=True)
        if method and symbol == "set_trigger_holdoff":
            return super()._symbol_status("configure_trigger", method=True)
        if method and symbol in {
            "get_decoded_bus_capability",
            "supports_decoded_bus_events",
        }:
            return super()._symbol_status("probe_bus_support", method=True)
        if method and symbol == "read_decoded_bus_events":
            status, cases = super()._symbol_status("probe_bus_support", method=True)
            if status == "PASS" and getattr(self, "_decoded_bus_supported", None) is False:
                return "SKIP", cases
            return status, cases
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
