"""Extract per-digit glyph templates from labeled loot frames.

Run once (or whenever new labeled samples exist):
    py tools/build_digit_templates.py

Reads a hardcoded list of (image path, roi, expected value) samples whose values
were verified visually / by stable multi-read, segments each number into glyphs
via connected components, and writes normalized 14x20 binary templates to
assets/digits/<digit>_<n>.png.
"""

from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from coclab.digits import NORM_SIZE, segment_glyphs  # noqa: E402

OUT_DIR = ROOT / "assets" / "digits"

GOLD_ROI = [0.050, 0.118, 0.183, 0.178]
ELIXIR_ROI = [0.050, 0.165, 0.183, 0.222]

SAMPLES: list[tuple[str, list[float], int]] = [
    # gold (verified via strip inspection / stable agreement)
    ("work/dev/run12_005.png", GOLD_ROI, 2194867),
    ("work/dev/run12_006.png", GOLD_ROI, 2194867),
    ("work/dev/run12_013.png", GOLD_ROI, 386921),
    ("work/dev/run12_016.png", GOLD_ROI, 1839970),
    ("work/dev/run12_022.png", GOLD_ROI, 524758),
    ("work/dev/run12_027.png", GOLD_ROI, 2019901),
    ("work/dev/run12_028.png", GOLD_ROI, 2019901),
    ("work/dev/run11_018.png", GOLD_ROI, 506372),
    ("work/dev/run7b_12.png", GOLD_ROI, 322243),
    # elixir rows (same font; values from verified logs)
    ("work/dev/run11_018.png", ELIXIR_ROI, 620490),
    ("work/dev/run7b_12.png", ELIXIR_ROI, 323888),
    ("work/dev/run12_022.png", ELIXIR_ROI, 491889),
]

NORM_SIZE = (14, 20)


def crop_percent(img: np.ndarray, x1: float, y1: float, x2: float, y2: float) -> np.ndarray:
    h, w = img.shape[:2]
    px1, py1 = int(x1 * w), int(y1 * h)
    px2, py2 = int(x2 * w), int(y2 * h)
    return img[py1:py2, px1:px2]


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    counters: dict[int, int] = {}
    total = 0
    for rel, roi, value in SAMPLES:
        path = ROOT / rel
        img = cv2.imread(str(path))
        if img is None:
            print(f"SKIP (missing): {rel}")
            continue
        crop = crop_percent(img, *roi)
        glyphs = segment_glyphs(crop)
        digits = str(value)
        if len(glyphs) != len(digits):
            print(
                f"FAIL {rel} roi={roi[1]:.3f} value={value}: "
                f"{len(glyphs)} glyphs != {len(digits)} digits"
            )
            continue
        print(f"OK   {rel} y={roi[1]:.3f} {value}: {len(digits)} glyphs")
        for ch, glyph in zip(digits, glyphs):
            norm = cv2.resize(glyph, NORM_SIZE, interpolation=cv2.INTER_AREA)
            _, norm = cv2.threshold(norm, 127, 255, cv2.THRESH_BINARY)
            d = int(ch)
            counters[d] = counters.get(d, 0) + 1
            out = OUT_DIR / f"{d}_{counters[d]:02d}.png"
            cv2.imwrite(str(out), norm)
            total += 1
    print(f"done: {total} templates in {OUT_DIR}")
    missing = [d for d in range(10) if d not in counters]
    if missing:
        print(f"WARNING missing digits: {missing}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
