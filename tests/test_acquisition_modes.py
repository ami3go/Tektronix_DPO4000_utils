from __future__ import annotations

import pytest

from dpo4000_utils.acquisition_modes import (
    AcquisitionModeReadbackMixin,
    canonicalize_acquisition_mode_readback,
)
from dpo4000_utils.control import (
    AcquisitionConfig,
    build_acquisition_mode_command,
    build_acquisition_setup_commands,
)
from dpo4000_utils.errors import DPOProtocolError


class _RawAcquisitionControl:
    def get_acquisition_setup(self) -> dict[str, str]:
        return {
            "mode": "HIR",
            "average_count": "16",
            "record_length": "1000",
        }

    def get_acquisition_mode(self) -> str:
        return "HIR"


class _CanonicalAcquisitionControl(AcquisitionModeReadbackMixin, _RawAcquisitionControl):
    pass


def test_tektronix_short_readback_is_canonicalized_to_hires():
    assert canonicalize_acquisition_mode_readback("HIR") == "HIRES"
    assert canonicalize_acquisition_mode_readback(":ACQuire:MODE HIR") == "HIRES"


def test_all_minimum_form_scope_readbacks_use_canonical_application_labels():
    assert canonicalize_acquisition_mode_readback("SAM") == "SAMPLE"
    assert canonicalize_acquisition_mode_readback("PEAK") == "PEAKDETECT"
    assert canonicalize_acquisition_mode_readback("HIR") == "HIRES"
    assert canonicalize_acquisition_mode_readback("AVE") == "AVERAGE"
    assert canonicalize_acquisition_mode_readback("ENV") == "ENVELOPE"


def test_readback_mixin_never_exposes_hir_to_callers():
    control = _CanonicalAcquisitionControl()

    assert control.get_acquisition_mode() == "HIRES"
    assert control.get_acquisition_setup()["mode"] == "HIRES"


def test_record_length_change_can_reuse_canonical_hires_readback():
    control = _CanonicalAcquisitionControl()
    mode = control.get_acquisition_setup()["mode"]

    assert build_acquisition_setup_commands(
        AcquisitionConfig(mode=mode, record_length="10k")
    ) == [
        "ACQUIRE:MODE HIRES",
        "HORIZONTAL:RECORDLENGTH 10000",
    ]


def test_hir_is_not_supported_as_application_or_api_input():
    with pytest.raises(ValueError, match="Unsupported acquisition mode"):
        build_acquisition_mode_command("HIR")


def test_unknown_scope_mode_readback_is_protocol_error():
    with pytest.raises(DPOProtocolError, match="Unsupported acquisition mode readback"):
        canonicalize_acquisition_mode_readback("UNKNOWN")
