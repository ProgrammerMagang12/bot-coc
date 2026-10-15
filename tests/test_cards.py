import cv2
import numpy as np

from coclab import cards


def _pattern() -> np.ndarray:
    tpl = np.full((20, 16), 255, np.uint8)
    tpl[5:15, 4:12] = 0
    return tpl


def test_detect_cards_finds_template(tmp_path):
    tpl = _pattern()
    cv2.imwrite(str(tmp_path / "alpha.png"), tpl)
    img = np.zeros((200, 300), np.uint8)
    img[120:140, 210:226] = tpl  # tempel di (210, 120)
    hits = cards.detect_cards(
        img, tmp_path, files={"alpha": "alpha.png"}, threshold=0.9
    )
    assert "alpha" in hits
    cx, cy, score = hits["alpha"]
    assert (cx, cy) == (218, 130)  # pusat template
    assert score > 0.99


def test_detect_cards_rejects_inverted_pattern(tmp_path):
    tpl = _pattern()
    cv2.imwrite(str(tmp_path / "alpha.png"), tpl)
    img = np.zeros((200, 300), np.uint8)
    img[120:140, 210:226] = 255 - tpl  # pola terbalik -> tidak cocok
    hits = cards.detect_cards(
        img, tmp_path, files={"alpha": "alpha.png"}, threshold=0.5
    )
    assert "alpha" not in hits


def test_detect_cards_respects_roi(tmp_path):
    tpl = _pattern()
    cv2.imwrite(str(tmp_path / "alpha.png"), tpl)
    img = np.zeros((200, 300), np.uint8)
    img[120:140, 210:226] = tpl

    miss = cards.detect_cards(
        img,
        tmp_path,
        files={"alpha": "alpha.png"},
        threshold=0.9,
        roi=[0.0, 0.0, 0.5, 1.0],  # kiri saja -> tidak ketemu
    )
    assert "alpha" not in miss

    found = cards.detect_cards(
        img,
        tmp_path,
        files={"alpha": "alpha.png"},
        threshold=0.9,
        roi=[0.6, 0.5, 1.0, 1.0],  # kanan bawah -> ketemu
    )
    assert "alpha" in found
    cx, cy, _ = found["alpha"]
    assert (cx, cy) == (218, 130)  # koordinat dalam ruang citra penuh


def test_detect_cards_skips_missing_template(tmp_path):
    img = np.zeros((100, 100), np.uint8)
    hits = cards.detect_cards(
        img, tmp_path, files={"ghost": "ghost.png"}, threshold=0.5
    )
    assert hits == {}


def test_detect_cards_skips_template_larger_than_image(tmp_path):
    tpl = _pattern()
    cv2.imwrite(str(tmp_path / "alpha.png"), tpl)
    img = np.zeros((10, 10), np.uint8)  # lebih kecil dari template
    hits = cards.detect_cards(
        img, tmp_path, files={"alpha": "alpha.png"}, threshold=0.5
    )
    assert hits == {}


def test_detect_cards_names_filter(tmp_path):
    tpl = _pattern()
    cv2.imwrite(str(tmp_path / "alpha.png"), tpl)
    img = np.zeros((200, 300), np.uint8)
    img[120:140, 210:226] = tpl
    hits = cards.detect_cards(
        img,
        tmp_path,
        names=["beta"],
        files={"alpha": "alpha.png", "beta": "alpha.png"},
        threshold=0.9,
    )
    assert "alpha" not in hits and "beta" in hits
