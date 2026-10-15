"""Template-based reader for CoC loot numbers (fixed font).

RapidOCR misreads some numbers in this font; connected-component segmentation +
per-digit template matching is deterministic. Templates live in assets/digits/
(built by tools/build_digit_templates.py).
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "assets" / "digits"
NORM_SIZE = (14, 20)  # (w, h)
MIN_GLYPHS, MAX_GLYPHS = 3, 7  # loot numbers are 3-7 digits

_templates: dict[int, list[np.ndarray]] | None = None


def _load_templates() -> dict[int, list[np.ndarray]]:
    global _templates
    if _templates is None:
        buckets: dict[int, list[np.ndarray]] = {}
        if TEMPLATE_DIR.is_dir():
            for path in sorted(TEMPLATE_DIR.glob("*.png")):
                try:
                    digit = int(path.name.split("_")[0])
                except ValueError:
                    continue
                img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
                if img is not None:
                    buckets.setdefault(digit, []).append(img)
        _templates = buckets
    return _templates


def segment_glyphs(crop: np.ndarray, min_height: int = 55, max_height: int = 92) -> list[np.ndarray]:
    """Glyph bitmaps left to right.

    Binarize after 4x cubic upscale (keeps inter-digit seams), keep components in
    the digit height band, then merge boxes that overlap in x (glyphs like "1"
    split into stem + flag pieces). Heights are measured at 4x; digits are ~74-78px.
    """
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    big_gray = cv2.resize(gray, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC)
    _, big = cv2.threshold(big_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    n, _labels, stats, _cent = cv2.connectedComponentsWithStats(big, 8)
    boxes: list[list[int]] = []
    for i in range(1, n):
        x, y, w, h, area = (int(v) for v in stats[i])
        if min_height <= h <= max_height and 18 <= w <= 220 and area >= 300:
            boxes.append([x, y, x + w, y + h])
    boxes.sort(key=lambda b: b[0])
    merged: list[list[int]] = []
    for box in boxes:
        if merged and box[0] <= merged[-1][2] - 3:  # x-overlap => same glyph
            merged[-1][1] = min(merged[-1][1], box[1])
            merged[-1][2] = max(merged[-1][2], box[2])
            merged[-1][3] = max(merged[-1][3], box[3])
        else:
            merged.append(box)
    return [big[y1:y2, x1:x2] for x1, y1, x2, y2 in merged]


def classify_glyph(glyph: np.ndarray) -> str | None:
    templates = _load_templates()
    if not templates:
        return None
    norm = cv2.resize(glyph, NORM_SIZE, interpolation=cv2.INTER_AREA)
    _, norm = cv2.threshold(norm, 127, 255, cv2.THRESH_BINARY)
    best_digit, best_score = None, -1.0
    for digit, samples in templates.items():
        for tmpl in samples:
            if tmpl.shape != norm.shape:
                tmpl = cv2.resize(tmpl, NORM_SIZE, interpolation=cv2.INTER_AREA)
            score = float(np.mean(norm == tmpl))
            if score > best_score:
                best_digit, best_score = digit, score
    return str(best_digit) if best_digit is not None else None


def read_loot_number(crop: np.ndarray) -> int | None:
    """Read a loot number crop; returns int or None when implausible."""
    glyphs = segment_glyphs(crop)
    if not MIN_GLYPHS <= len(glyphs) <= MAX_GLYPHS:
        logger.info("loot digits: implausible glyph count %d", len(glyphs))
        return None
    digits = []
    for glyph in glyphs:
        d = classify_glyph(glyph)
        if d is None:
            logger.info("loot digits: template set unavailable")
            return None
        digits.append(d)
    return int("".join(digits))
