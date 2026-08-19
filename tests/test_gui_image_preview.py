import pytest

from dpo4000_utils.gui.image_preview import subsample_factor, usable_preview_size


def test_usable_preview_size_uses_fallback_when_widget_is_not_ready():
    size = usable_preview_size(1, 1)
    assert size.width == 808
    assert size.height == 488


def test_usable_preview_size_keeps_minimum_size():
    size = usable_preview_size(30, 30)
    assert size.width == 120
    assert size.height == 90


def test_subsample_factor_returns_one_for_small_image():
    assert subsample_factor(320, 200, 640, 480) == 1


def test_subsample_factor_rounds_up_to_fit():
    assert subsample_factor(1920, 1080, 800, 500) == 3


def test_subsample_factor_rejects_invalid_dimensions():
    with pytest.raises(ValueError):
        subsample_factor(0, 100, 800, 500)
