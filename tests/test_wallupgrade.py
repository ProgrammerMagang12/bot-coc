import dataclasses
from pathlib import Path

import numpy as np

from coclab import wallupgrade
from coclab.config import load_config
from coclab.vision import Match

EXAMPLE = Path(__file__).parent.parent / "config.example.json"


class Env:
    def __init__(self, gold, wall_after, logo_found):
        self.gold = gold
        self.wall_after = wall_after  # iterasi (1-based) saat kata "wall" terlihat; None = tak pernah
        self.logo_found = logo_found
        self.checks = 0
        self.taps_px = []
        self.taps_pct = []
        self.swipes = []
        self.sleeps = []

    def capture(self, name):
        return Path(f"fake/{name}")

    def load_image(self, path):
        return np.zeros((100, 100, 3), np.uint8)

    def find_template(self, shot, template):
        return Match(self.logo_found, 50, 60, 0.95)

    def crop_percent(self, img, *roi):
        return img

    def ocr_boxes(self, crop):
        self.checks += 1
        visible = self.wall_after is not None and self.checks >= self.wall_after
        return [("Upgrade Wall", 30, 25)] if visible else [("Upgrade Archer Tower", 30, 25)]

    def read_gold(self, crop):
        return self.gold

    def tap_px(self, x, y):
        self.taps_px.append((x, y))

    def tap_percent(self, xp, yp):
        self.taps_pct.append((xp, yp))

    def swipe_percent(self, x1p, y1p, x2p, y2p):
        self.swipes.append((x1p, y1p, x2p, y2p))

    def sleep(self, seconds):
        self.sleeps.append(seconds)


def _wall_cfg(enabled=True):
    return dataclasses.replace(load_config(EXAMPLE).wall_upgrade, enabled=enabled)


def _run(env, cfg=None):
    cfg = cfg or _wall_cfg()
    return wallupgrade.run_wall_upgrade(
        cfg,
        capture=env.capture,
        load_image=env.load_image,
        find_template=env.find_template,
        crop_percent=env.crop_percent,
        ocr_boxes=env.ocr_boxes,
        read_gold=env.read_gold,
        tap_px=env.tap_px,
        tap_percent=env.tap_percent,
        swipe_percent=env.swipe_percent,
        sleep=env.sleep,
    )


def test_disabled_skips():
    env = Env(gold=9_999_999, wall_after=1, logo_found=True)
    result = _run(env, _wall_cfg(enabled=False))
    assert result.status == "skipped" and "disabled" in result.reason


def test_low_gold_skips():
    env = Env(gold=1_000_000, wall_after=1, logo_found=True)
    result = _run(env)
    assert result.status == "skipped" and "gold" in result.reason


def test_missing_logo_fails():
    env = Env(gold=3_000_000, wall_after=1, logo_found=False)
    result = _run(env)
    assert result.status == "failed" and "logo" in result.reason


def test_upgrade_sequence_first_try():
    env = Env(gold=3_000_000, wall_after=1, logo_found=True)
    result = _run(env)
    cfg = _wall_cfg()
    assert result.status == "upgraded"
    assert env.swipes == []
    assert env.taps_px[0] == (50, 60)  # klik logo dari match center
    assert env.taps_px[1] == (34 + 30, 13 + 25)  # klik teks "wall" (roi offset + box center)
    assert env.taps_pct == [
        tuple(cfg.gold_upgrade_point),
        tuple(cfg.gold_confirm_point),
        tuple(cfg.elixir_upgrade_point),
        tuple(cfg.elixir_confirm_point),
    ]


def test_found_after_scroll():
    env = Env(gold=3_000_000, wall_after=3, logo_found=True)
    result = _run(env)
    assert result.status == "upgraded" and len(env.swipes) == 2


def test_exhausted_scroll_fails():
    env = Env(gold=3_000_000, wall_after=None, logo_found=True)
    result = _run(env)
    assert result.status == "failed" and "not found" in result.reason
    assert len(env.swipes) == _wall_cfg().max_scroll_tries - 1
