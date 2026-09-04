from __future__ import annotations

import pytest

from dpo4000_utils.automation import BurstConfig


def test_a7_review_rejects_fractional_count() -> None:
    with pytest.raises(ValueError, match="positive integer"):
        BurstConfig(1.5, 0.0)


def test_a7_review_requires_boolean_single_setting() -> None:
    with pytest.raises(ValueError, match="must be boolean"):
        BurstConfig(1, 0.0, single_acquisition="false")
