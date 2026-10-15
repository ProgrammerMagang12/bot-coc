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


def enhance_numeric_crop(img: np.ndarray, upscale: int = 4) -> np.ndarray:
    """Binarize (Otsu) + invert + upscale — helps OCR read game-styled numbers."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    inverted = cv2.bitwise_not(binary)
    big = cv2.resize(
        inverted, None, fx=upscale, fy=upscale, interpolation=cv2.INTER_LANCZOS4
    )
    return cv2.cvtColor(big, cv2.COLOR_GRAY2BGR)


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


def _looks_like_thousands_groups(tokens: list[str]) -> bool:
    """True for '1 369 204' / '1369 204' — one number split by thousands separators."""
    if not all(token.isdigit() for token in tokens):
        return False
    if len(tokens) > 4:
        return False
    if not 1 <= len(tokens[0]) <= 4:
        return False
    rest = tokens[1:]
    if not rest or len(rest[-1]) != 3:
        return False
    return all(len(token) == 3 for token in rest)


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
    if not numeric_tokens:
        logger.info("OCR: no numeric field found (raw=%r)", text)
        return None
    if len(numeric_tokens) == 1:
        digits = "".join(ch for ch in numeric_tokens[0] if ch.isdigit())
    elif _looks_like_thousands_groups(numeric_tokens):
        digits = "".join(numeric_tokens)
    else:
        logger.info(
            "OCR: expected exactly one numeric field, found %d (raw=%r)",
            len(numeric_tokens),
            text,
        )
        return None
    if not digits or len(digits) > _MAX_DIGITS:
        return None
    return int(digits)


_boxes_engine_cache: list[Callable[[np.ndarray], list[tuple[str, int, int]]] | None] = []


def _try_create_boxes_engine():
    """Load rapidocr once; returns callable(img) -> [(text, cx, cy), ...] or None."""
    try:
        from rapidocr_onnxruntime import RapidOCR  # type: ignore[import-not-found]
    except ImportError:
        logger.warning("rapidocr-onnxruntime not installed; text OCR is disabled")
        return None

    ocr = RapidOCR()

    def run(image: np.ndarray) -> list[tuple[str, int, int]]:
        result, _elapsed = ocr(image)
        boxes: list[tuple[str, int, int]] = []
        if not result:
            return boxes
        for item in result:
            points, text = item[0], str(item[1])
            xs = [float(p[0]) for p in points]
            ys = [float(p[1]) for p in points]
            boxes.append((text, int(sum(xs) / len(xs)), int(sum(ys) / len(ys))))
        return boxes

    return run


def _load_boxes_engine():
    if not _boxes_engine_cache:
        _boxes_engine_cache.append(_try_create_boxes_engine())
    return _boxes_engine_cache[0]


def ocr_text_boxes(
    img: np.ndarray | None, engine=None
) -> list[tuple[str, int, int]]:
    """OCR text with box centers. Returns [] when the engine is unavailable."""
    if engine is None:
        engine = _load_boxes_engine()
        if engine is None:
            return []
    try:
        return list(engine(img) or [])
    except Exception as exc:  # noqa: BLE001 - OCR failures must not crash the loop
        logger.warning("text OCR failed: %s", exc)
        return []


def ocr_text(img: np.ndarray | None, engine=None) -> str:
    """Joined OCR text; the optional engine has the same contract as ocr_text_boxes."""
    return " ".join(text for text, _x, _y in ocr_text_boxes(img, engine))
