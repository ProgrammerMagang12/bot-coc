import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

import picker  # noqa: E402


def test_scale_factor_fits_large_image():
    assert picker.scale_factor(3200, 1800, 1280, 700) == pytest.approx(700 / 1800)


def test_scale_factor_keeps_small_image():
    assert picker.scale_factor(800, 600) == 1.0


def test_display_to_image_roundtrip():
    assert picker.display_to_image(640, 350, 0.5) == (1280, 700)
    assert picker.display_to_image(10, 10, 1.0) == (10, 10)


def test_display_to_image_guards_bad_scale():
    assert picker.display_to_image(10, 10, 0) == (10, 10)
