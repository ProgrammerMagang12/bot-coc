import sys

import cv2
import numpy as np

sys.path.insert(0, "tools")

import make_template as mt


def test_crop_and_save_writes_selected_region(tmp_path):
    img = np.zeros((100, 200, 3), np.uint8)
    img[10:30, 50:150] = 255
    src = tmp_path / "s.png"
    cv2.imwrite(str(src), img)
    out = tmp_path / "t.png"
    mt.crop_and_save(src, (50, 10, 100, 20), out)
    saved = cv2.imread(str(out))
    assert saved.shape[:2] == (20, 100) and saved.mean() > 250


def test_region_percent_roundtrip():
    p = mt.region_percent((50, 10, 100, 20), (200, 100))
    assert p == (0.25, 0.1, 0.75, 0.3)
