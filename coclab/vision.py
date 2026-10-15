"""Vision primitives: template matching and image validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


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
