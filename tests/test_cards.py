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


def test_verify_deck_ok_when_all_strict_present():
    detected = {"dragon": (170, 815, 0.9), "balloon": (291, 815, 0.9),
                "rage": (1180, 815, 0.9), "freeze": (1301, 815, 0.9),
                "extra_pink": (421, 815, 0.9)}
    army = {"rage_spell": 4, "freeze_spell": 3, "extra_troop": 5}
    check = cards.verify_deck(detected, army, ["dragon", "balloon", "extra", "rage", "freeze"],
                              extra_template="extra_pink")
    assert check.ok and check.problems == []


def test_verify_deck_flags_missing_strict_type():
    detected = {"dragon": (170, 815, 0.9), "balloon": (291, 815, 0.9)}
    army = {"rage_spell": 4, "freeze_spell": 3}
    check = cards.verify_deck(detected, army, ["dragon", "balloon", "rage", "freeze"])
    assert not check.ok and check.problems == ["rage", "freeze"]


def test_verify_deck_extra_soft_without_template():
    detected = {"dragon": (0, 0, 0.9), "balloon": (0, 0, 0.9)}
    check = cards.verify_deck(detected, {}, ["dragon", "balloon", "extra"], extra_template=None)
    assert check.ok and check.soft_missing == ["extra"]


def test_verify_deck_rage_not_required_when_zero_comp():
    detected = {"dragon": (0, 0, 0.9), "balloon": (0, 0, 0.9)}
    check = cards.verify_deck(detected, {"rage_spell": 0, "freeze_spell": 0},
                              ["dragon", "balloon", "rage", "freeze"])
    assert check.ok


def test_verify_deck_ignores_unknown_strict_type():
    detected = {"dragon": (0, 0, 0.9), "balloon": (0, 0, 0.9)}
    check = cards.verify_deck(detected, {}, ["dragon", "balloon", "wall_wrecker"])
    assert check.ok and check.notes["ignored"] == ["wall_wrecker"]


def test_verify_deck_template_missing_goes_soft():
    detected = {"dragon": (0, 0, 0.9), "balloon": (0, 0, 0.9)}
    available = {"dragon", "balloon", "rage"}  # freeze tidak tersedia
    check = cards.verify_deck(detected, {"freeze_spell": 3}, ["dragon", "balloon", "freeze"],
                              available=available)
    assert check.ok and check.soft_missing == ["freeze"]


def test_count_roi_around_center():
    x1, y1, x2, y2 = cards.count_roi(170, 815)
    assert (x1, y1, x2, y2) == (128, 741, 212, 771)
