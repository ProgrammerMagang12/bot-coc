"""Vision primitives: template matching, cropping and digit OCR."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_MAX_DIGITS = 9


@dataclass
class Match:
    found: bool
    cx: int
    cy: int
    score: float


def load_image(path: str | Path) -> np.ndarray:
    """Load an image as BGR. Raises ValueError when unreadable."""
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        raise ValueError(f"cannot read image: {path}")
    return image


def is_valid_image(path: str | Path) -> bool:
    """True when the file exists and decodes to a non-empty image."""
    if not Path(path).is_file():
        return False
    try:
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    except cv2.error:
        return False
    return image is not None and image.size > 0


def find_template(img: np.ndarray, tpl: np.ndarray, threshold: float) -> Match:
    """Locate tpl inside img. Returns the match center and normalized score."""
    if tpl.shape[0] > img.shape[0] or tpl.shape[1] > img.shape[1]:
        return Match(False, 0, 0, 0.0)

    result = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    score = float(max_val) if max_val == max_val else 0.0  # NaN guard
    cx = int(max_loc[0] + tpl.shape[1] // 2)
    cy = int(max_loc[1] + tpl.shape[0] // 2)
    return Match(score >= threshold, cx, cy, score)


def crop_percent(
    img: np.ndarray, x1: float, y1: float, x2: float, y2: float
) -> np.ndarray:
    """Crop a percent-based region, clamped to the image bounds, at least 1x1."""
    height, width = img.shape[:2]
    px1 = max(0, min(width - 1, int(x1 * width)))
    py1 = max(0, min(height - 1, int(y1 * height)))
    px2 = max(px1 + 1, min(width, int(x2 * width)))
    py2 = max(py1 + 1, min(height, int(y2 * height)))
    return img[py1:py2, px1:px2]


_engine_cache: list[Callable[[np.ndarray], str] | None] = []


def _try_create_engine() -> Callable[[np.ndarray], str] | None:
    """Load rapidocr when installed; otherwise warn and disable OCR."""
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-not-found]
    except ImportError:
        logger.warning("rapidocr-onnxruntime not installed; OCR is disabled")
        return None

    ocr = RapidOCR()

    def run(image: np.ndarray) -> str:
        result, _elapsed = ocr(image)
        if not result:
            return ""
        return " ".join(str(item[1]) for item in result)

    return run


def _load_default_engine() -> Callable[[np.ndarray], str] | None:
    """Return the process-wide default engine, creating it at most once."""
    if not _engine_cache:
        _engine_cache.append(_try_create_engine())
    return _engine_cache[0]


def ocr_digits(
    img: np.ndarray | None, engine: Callable[[np.ndarray | None], str] | None = None
) -> int | None:
    """Return digits found by the engine as int, or None when unavailable/implausible."""
    if engine is None:
        engine = _load_default_engine()
        if engine is None:
            return None
    try:
        text = engine(img) or ""
    except Exception as exc:  # noqa: BLE001 - engine failures must not crash the loop
        logger.warning("OCR failed: %s", exc)
        return None
    numeric_tokens = [
        token for token in text.split() if any(ch.isdigit() for ch in token)
    ]
    if len(numeric_tokens) != 1:
        logger.info(
            "OCR: expected exactly one numeric field, found %d (raw=%r)",
            len(numeric_tokens),
            text,
        )
        return None
    digits = "".join(ch for ch in numeric_tokens[0] if ch.isdigit())
    if not digits or len(digits) > _MAX_DIGITS:
        return None
    return int(digits)
