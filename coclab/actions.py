"""Physical action gate: observe only logs, live taps for real."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

MODES = ("observe", "live")


class Actions:
    """Every physical action goes through this gate."""

    def __init__(self, adb, device: str, mode: str, screen: tuple[int, int]) -> None:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {mode!r}")
        self.adb = adb
        self.device = device
        self.mode = mode
        self.screen = screen

    def tap_percent(self, xp: float, yp: float) -> None:
        x = int(xp * self.screen[0])
        y = int(yp * self.screen[1])
        self.tap_px(x, y)

    def tap_px(self, x: int, y: int) -> None:
        if self.mode == "observe":
            logger.info("[OBSERVE] tap (%d, %d)", x, y)
            return
        self.adb.tap(self.device, x, y)
