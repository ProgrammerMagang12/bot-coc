"""Template-based reader for CoC loot numbers (fixed font).

RapidOCR misreads some numbers in this font; connected-component segmentation +
per-digit template matching is deterministic. Templates live in assets/digits/
(built by tools/build_digit_templates.py).
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

from coclab.paths import base_dir

logger = logging.getLogger(__name__)

TEMPLATE_DIR = base_dir() / "assets" / "digits"
NORM_SIZE = (14, 20)  # (w, h)
MIN_GLYPHS, MAX_GLYPHS = 3, 7  # loot numbers are 3-7 digits
MIN_SCORE = 0.80  # real digits score ~0.95-1.0; background blobs ~0.6

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


def segment_glyphs(
    crop: np.ndarray, scale: int = 4, min_height: int | None = None, max_height: int | None = None
) -> list[np.ndarray]:
    """Glyph bitmaps left to right.

    Binarize after `scale`x cubic upscale (keeps inter-digit seams), keep
    components in the digit height band, then merge boxes that overlap in x
    (glyphs like "1" split into stem + flag pieces). Band bounds are calibrated
    for scale=4 (digit height ~74-78px there) and adjusted proportionally.
    """
    if min_height is None:
        min_height = int(55 * scale / 4)
    if max_height is None:
        max_height = int(92 * scale / 4)
    area_min = int(300 * (scale / 4) ** 2)
    min_w = max(10, int(18 * scale / 4))
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    big_gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    _, big = cv2.threshold(big_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    n, _labels, stats, _cent = cv2.connectedComponentsWithStats(big, 8)
    boxes: list[list[int]] = []
    for i in range(1, n):
        x, y, w, h, area = (int(v) for v in stats[i])
        if min_height <= h <= max_height and min_w <= w <= 220 and area >= area_min:
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
    """Best-matching digit, or None when below the confidence threshold (junk blob)."""
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
    if best_digit is None or best_score < MIN_SCORE:
        return None
    return str(best_digit)


def read_loot_number(
    crop: np.ndarray,
    scale: int = 4,
    min_digits: int = MIN_GLYPHS,
    max_digits: int = MAX_GLYPHS,
    min_height: int | None = None,
    max_height: int | None = None,
) -> int | None:
    """Read a loot number crop; returns int or None when implausible.

    Blobs below the classification confidence threshold are dropped as debris
    (rocks/grass); real glyphs score far above it. `scale` adapts to font size
    (4 = loot panel/badge, 3 = home resource bars)."""
    glyphs = segment_glyphs(
        crop, scale=scale, min_height=min_height, max_height=max_height
    )
    digits: list[str] = []
    skipped = 0
    for glyph in glyphs:
        d = classify_glyph(glyph)
        if d is None:
            skipped += 1
            continue
        digits.append(d)
    if skipped:
        logger.info("loot digits: skipped %d non-digit blob(s)", skipped)
    if not min_digits <= len(digits) <= max_digits:
        logger.info("loot digits: implausible glyph count %d", len(digits))
        return None
    return int("".join(digits))


def read_badge_number(crop: np.ndarray) -> int | None:
    """Small counts like card badges 'x13' (1-3 digits)."""
    return read_loot_number(crop, min_digits=1, max_digits=3)


def read_home_number(crop: np.ndarray) -> int | None:
    """Home resource bar numbers (font ~26px → glyphs 76-79 at 4x, default band)."""
    return read_loot_number(crop, min_digits=2, max_digits=8)
