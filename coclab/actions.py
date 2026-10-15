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

    def swipe_percent(self, x1p: float, y1p: float, x2p: float, y2p: float) -> None:
        self.swipe_px(
            int(x1p * self.screen[0]),
            int(y1p * self.screen[1]),
            int(x2p * self.screen[0]),
            int(y2p * self.screen[1]),
        )

    def swipe_px(self, x1: int, y1: int, x2: int, y2: int) -> None:
        if self.mode == "observe":
            logger.info("[OBSERVE] swipe (%d, %d) -> (%d, %d)", x1, y1, x2, y2)
            return
        self.adb.swipe(self.device, x1, y1, x2, y2)
