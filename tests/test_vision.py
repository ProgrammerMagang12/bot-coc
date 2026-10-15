import cv2
import numpy as np
import pytest

from coclab.vision import crop_percent, find_template, is_valid_image, load_image, ocr_digits


def _canvas_with_block(cx, cy, size=24):
    rng = np.random.default_rng(42)
    img = rng.integers(0, 255, (200, 300, 3), dtype=np.uint8)  # tekstur: hindari window konstan
    tpl = np.full((size, size, 3), (0, 0, 255), np.uint8)
    tpl[: size // 4, : size // 4] = (255, 255, 255)  # marker: template tidak konstan
    img[cy : cy + size, cx : cx + size] = tpl
    return img, tpl


def test_find_template_exact_position():
    img, tpl = _canvas_with_block(120, 60)
    m = find_template(img, tpl, 0.9)
    assert m.found and m.score > 0.99
    assert abs(m.cx - (120 + 12)) <= 1 and abs(m.cy - (60 + 12)) <= 1  # center


def test_find_template_negative():
    img, tpl = _canvas_with_block(120, 60)
    other = np.full((24, 24, 3), (0, 255, 0), np.uint8)
    other[: 6, : 6] = (255, 255, 255)
    m = find_template(img, other, 0.9)
    assert not m.found and m.score < 0.9


def test_find_template_rejects_oversized_template():
    img = np.zeros((50, 50, 3), np.uint8)
    tpl = np.zeros((80, 80, 3), np.uint8)
    m = find_template(img, tpl, 0.9)
    assert not m.found and m.score == 0.0  # tidak boleh crash


def test_is_valid_image_rejects_truncated(tmp_path):
    img, _ = _canvas_with_block(10, 10)
    ok = tmp_path / "ok.png"
    cv2.imwrite(str(ok), img)
    raw = ok.read_bytes()
    bad = tmp_path / "bad.png"
    bad.write_bytes(raw[: len(raw) // 3])
    assert is_valid_image(ok) is True
    assert is_valid_image(bad) is False  # Review Focus #2
    assert is_valid_image(tmp_path / "missing.png") is False


def test_load_image_returns_bgr_array(tmp_path):
    img, _ = _canvas_with_block(10, 10)
    p = tmp_path / "x.png"
    cv2.imwrite(str(p), img)
    arr = load_image(p)
    assert arr.shape == (200, 300, 3)


def test_crop_percent_region_math():
    img = np.zeros((100, 200, 3), np.uint8)
    img[20:30, 40:140] = 255  # region y 0.2-0.3, x 0.2-0.7
    out = crop_percent(img, 0.2, 0.2, 0.7, 0.3)
    assert out.shape[:2] == (10, 100) and out.mean() > 250


def test_crop_percent_clamps_out_of_range():
    img = np.zeros((100, 100, 3), np.uint8)
    out = crop_percent(img, 0.9, 0.9, 1.4, 1.4)  # tidak boleh crash
    assert out.size > 0


def test_ocr_digits_joins_digits_and_ignores_noise():
    fake = lambda _img: "1,234,567 o"
    assert ocr_digits(None, engine=fake) == 1234567


def test_ocr_digits_extreme_length_returns_none():
    fake = lambda _img: "12345678901"  # 11 digit, Review Focus #4
    assert ocr_digits(None, engine=fake) is None


def test_ocr_digits_no_digit_returns_none():
    assert ocr_digits(None, engine=lambda _i: "loot") is None


def test_ocr_digits_real_engine_is_lazy_when_unavailable(monkeypatch):
    from coclab import vision

    monkeypatch.setattr(vision, "_load_default_engine", lambda: None)
    assert vision.ocr_digits(np.zeros((10, 10, 3), np.uint8)) is None
