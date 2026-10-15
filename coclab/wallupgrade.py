"""Wall upgrade after battle: gold check, OCR wall search, gold then elixir upgrade."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from coclab.config import WallUpgradeConfig
from coclab.vision import Match

logger = logging.getLogger(__name__)


@dataclass
class WallResult:
    status: str  # "skipped" | "upgraded" | "failed"
    reason: str = ""


def run_wall_upgrade(
    wall_cfg: WallUpgradeConfig,
    *,
    capture: Callable[[str], Path | None],
    load_image: Callable[[Path], object],
    find_template: Callable[[Path, str], Match],
    crop_percent: Callable[..., object],
    ocr_boxes: Callable[[object], list[tuple[str, int, int]]],
    read_gold: Callable[[object], int | None],
    tap_px: Callable[[int, int], None],
    tap_percent: Callable[[float, float], None],
    swipe_percent: Callable[[float, float, float, float], None],
    sleep: Callable[[float], None],
) -> WallResult:
    """Run the wall upgrade flow. Never raises for step failures."""
    if not wall_cfg.enabled:
        return WallResult("skipped", "wall upgrade disabled")

    gold_shot = capture("wall_gold.png")
    if gold_shot is None:
        return WallResult("failed", "home capture failed")
    crop = crop_percent(load_image(gold_shot), *wall_cfg.gold_storage_roi)
    gold = read_gold(crop)
    if gold is None:
        return WallResult("failed", "gold OCR unreadable")
    logger.info("Wall check: gold = %s (min %s)", gold, wall_cfg.gold_min)
    if gold < wall_cfg.gold_min:
        return WallResult("skipped", f"gold {gold} < {wall_cfg.gold_min}")

    logo_shot = capture("wall_logo.png")
    if logo_shot is None:
        return WallResult("failed", "logo capture failed")
    logo = find_template(logo_shot, wall_cfg.upgrade_logo)
    if not logo.found:
        return WallResult("failed", "upgrade logo not found")
    tap_px(logo.cx, logo.cy)
    logger.info("Open wall upgrade UI")
    sleep(1.0)

    centre_x = (wall_cfg.wall_text_roi[0] + wall_cfg.wall_text_roi[2]) / 2
    centre_y = (wall_cfg.wall_text_roi[1] + wall_cfg.wall_text_roi[3]) / 2

    for attempt in range(wall_cfg.max_scroll_tries):
        text_shot = capture("wall_text.png")
        if text_shot is None:
            return WallResult("failed", "wall text capture failed")
        image = load_image(text_shot)
        height, width = image.shape[:2]
        text_crop = crop_percent(image, *wall_cfg.wall_text_roi)
        offset_x = int(wall_cfg.wall_text_roi[0] * width)
        offset_y = int(wall_cfg.wall_text_roi[1] * height)
        for text, cx, cy in ocr_boxes(text_crop):
            if "wall" in text.lower():
                tap_px(offset_x + cx, offset_y + cy)
                logger.info("Click 'wall' text at (%d, %d)", offset_x + cx, offset_y + cy)
                sleep(0.8)
                tap_percent(*wall_cfg.gold_upgrade_point)
                logger.info("Select Gold upgrade")
                sleep(0.9)
                tap_percent(*wall_cfg.gold_confirm_point)
                logger.info("Gold upgrade done")
                sleep(2.0)
                tap_percent(*wall_cfg.elixir_upgrade_point)
                logger.info("Select Elixir upgrade")
                sleep(0.9)
                tap_percent(*wall_cfg.elixir_confirm_point)
                logger.info("Elixir upgrade done")
                sleep(2.0)
                return WallResult("upgraded")
        if attempt < wall_cfg.max_scroll_tries - 1:
            swipe_percent(centre_x, centre_y + 0.05, centre_x, centre_y - 0.05)
            sleep(1.0)
    return WallResult("failed", "wall text not found after scroll/OCR")
