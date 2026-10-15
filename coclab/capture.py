"""Screenshot capture with bounded retries and image validation."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from coclab.vision import is_valid_image

logger = logging.getLogger(__name__)


def capture(
    adb, device: str, dest: str | Path, retries: int = 2, sleep=time.sleep
) -> bool:
    """Capture a valid screenshot. Returns True on first valid image."""
    for attempt in range(retries + 1):
        try:
            adb.screencap(device, dest)
            if is_valid_image(dest):
                return True
            logger.warning(
                "capture attempt %d/%d: invalid image at %s",
                attempt + 1,
                retries + 1,
                dest,
            )
        except Exception as exc:  # noqa: BLE001 - retry instead of crashing
            logger.warning(
                "capture attempt %d/%d failed: %s", attempt + 1, retries + 1, exc
            )
        if attempt < retries:
            sleep(0.2)
    return False
