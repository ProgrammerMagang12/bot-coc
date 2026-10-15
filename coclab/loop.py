"""Bot orchestration: the v1 state machine with injected dependencies."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from coclab import vision, wallupgrade
from coclab.actions import Actions
from coclab.adb import Adb, AdbError
from coclab.capture import capture as capture_default
from coclab.config import Config
from coclab.state import BotState, StepResult
from coclab.strategy import load_strategies as load_strategies_default

logger = logging.getLogger(__name__)

_FIND_ATTACK_TRIES = 3
_MAX_LOOT_ROUNDS = 25


@dataclass
class RunSummary:
    ok: bool
    cycles_done: int
    reason: str = ""


@dataclass
class Deps:
    adb: object
    capture_fn: Callable[..., bool]
    load_image: Callable[..., object]
    find_template: Callable[..., vision.Match]
    crop_percent: Callable[..., object]
    ocr_digits: Callable[..., int | None]
    actions_factory: Callable[..., object]
    load_strategies: Callable[[str], list]
    sleep: Callable[[float], None]
    monotonic: Callable[[], float]
    state_hook: Callable[[str], None]


def _default_deps(config: Config) -> Deps:
    def find_template(img, tpl_path, threshold):
        return vision.find_template(img, vision.load_image(tpl_path), threshold)

    return Deps(
        adb=Adb(config.adb_path),
        capture_fn=capture_default,
        load_image=vision.load_image,
        find_template=find_template,
        crop_percent=vision.crop_percent,
        ocr_digits=vision.ocr_digits,
        actions_factory=Actions,
        load_strategies=load_strategies_default,
        sleep=time.sleep,
        monotonic=time.monotonic,
        state_hook=lambda name: logger.info("STATE %s", name),
    )


def _safe_dir_name(device: str) -> str:
    return device.replace(".", "_").replace(":", "_")


class _Session:
    def __init__(self, config: Config, mode: str, deps: Deps) -> None:
        self.cfg = config
        self.mode = mode
        self.deps = deps
        self.assets = Path(config.assets_dir)
        self.device: str = ""
        self.actions = None
        self.workdir: Path = Path(config.workdir)

    # -- helpers ---------------------------------------------------------

    def _state(self, state: BotState) -> None:
        self.deps.state_hook(state.name)

    def _capture(self, name: str) -> Path | None:
        dest = self.workdir / name
        if self.deps.capture_fn(self.deps.adb, self.device, dest):
            return dest
        return None

    def _img(self, shot: Path):
        return self.deps.load_image(shot)

    def _match(self, shot: Path, template: str) -> vision.Match:
        return self.deps.find_template(
            self._img(shot), self.assets / template, self.cfg.threshold
        )

    def _match_safe(self, shot: Path, template: str) -> vision.Match:
        """Like _match but treats an unavailable template file as not-found."""
        if not (self.assets / template).is_file():
            return vision.Match(False, 0, 0, 0.0)
        try:
            return self._match(shot, template)
        except ValueError as exc:
            logger.info("Template %s unreadable (%s); skipped", template, exc)
            return vision.Match(False, 0, 0, 0.0)

    # -- steps -----------------------------------------------------------

    def connect(self) -> StepResult:
        self._state(BotState.CONNECT)
        try:
            self.device = self.deps.adb.connect(self.cfg.device_address)
        except AdbError as exc:
            return StepResult(False, f"adb connect failed: {exc}")
        logger.info("Connected to %s", self.device)
        return StepResult(True)

    def prepare(self) -> StepResult:
        self._state(BotState.PREPARE)
        width, height = self.deps.adb.wm_size(self.device)
        logger.info("Screen %dx%d", width, height)
        self.actions = self.deps.actions_factory(
            self.deps.adb, self.device, self.mode, (width, height)
        )
        self.workdir = Path(self.cfg.workdir) / _safe_dir_name(self.device)
        self.workdir.mkdir(parents=True, exist_ok=True)
        return StepResult(True)

    def find_attack(self) -> StepResult:
        self._state(BotState.FIND_ATTACK)
        for _ in range(_FIND_ATTACK_TRIES):
            shot = self._capture("screen.png")
            if shot is None:
                return StepResult(False, "attack screen capture failed")
            match = self._match(shot, "attack.png")
            if match.found:
                logger.info("Attack button found (score %.2f)", match.score)
                return StepResult(True, data={"px": match.cx, "py": match.cy})
            self.deps.sleep(2)
        return StepResult(False, "attack button not found after retries")

    def matchmaking(self) -> StepResult:
        self._state(BotState.MATCHMAKING)
        shot = self._capture("matchmaking.png")
        if shot is None:
            return StepResult(False, "matchmaking capture failed")
        match = self._match(shot, "find_match.png")
        if match.found:
            self.actions.tap_px(match.cx, match.cy)
            logger.info("Click Find Match")
            self.deps.sleep(1.0)
            confirm_shot = self._capture("matchmaking_confirm.png")
            if confirm_shot is not None:
                confirm = self._match_safe(confirm_shot, "attack2.png")
                if confirm.found:
                    self.actions.tap_px(confirm.cx, confirm.cy)
                    logger.info("Click Attack (confirm)")
                    self.deps.sleep(1.0)
        deadline = self.deps.monotonic() + self.cfg.search_timeout_s
        while True:
            shot = self._capture("searching.png")
            if shot is None:
                return StepResult(False, "search screen capture failed")
            if self._match_safe(shot, "next.png").found:
                logger.info("Opponent found (Next button visible)")
                return StepResult(True)
            if self.deps.monotonic() > deadline:
                return StepResult(False, "opponent search timeout")
            logger.info("Searching opponent...")
            self.deps.sleep(2)

    _LOOT_VARIANTS = (4, 6)

    def _read_variant(self, img, roi: list[float], upscale: int) -> int | None:
        crop = self.deps.crop_percent(img, *roi)
        return self.deps.ocr_digits(vision.enhance_numeric_crop(crop, upscale=upscale))

    def _read_verified(self, roi: list[float]) -> int | None:
        """Two captures x two enhancement variants; accept only on agreement."""
        for attempt in range(2):
            shot = self._capture("loot.png")
            if shot is None:
                return None
            img = self._img(shot)
            values = [
                self._read_variant(img, roi, upscale) for upscale in self._LOOT_VARIANTS
            ]
            parsed = [v for v in values if v is not None]
            if len(parsed) == 2 and parsed[0] == parsed[1]:
                return parsed[0]
            if attempt == 0:
                logger.info("Loot read unconfirmed (%s); re-capturing", values)
                self.deps.sleep(1.0)
        return None

    def evaluate_loot(self) -> StepResult:
        self._state(BotState.LOOT_CHECK)
        self.deps.sleep(self.cfg.loot_settle_s)
        gold = self._read_verified(self.cfg.loot_roi)
        elixir = (
            self._read_verified(self.cfg.loot_roi_elixir) if gold is not None else None
        )
        if gold is None or elixir is None:
            if self.cfg.on_ocr_fail == "stop":
                return StepResult(False, "OCR unavailable (policy: stop)")
            if self.cfg.on_ocr_fail == "next":
                logger.warning("Loot OCR unavailable; skipping base (policy: next)")
                return StepResult(False, "loot_low")
            logger.warning("OCR unavailable; continuing (policy: attack)")
            return StepResult(True)
        logger.info(
            "Loot: gold %s (min %s) | elixir %s (min %s)",
            gold,
            self.cfg.min_gold,
            elixir,
            self.cfg.min_elixir,
        )
        if gold >= self.cfg.min_gold and elixir >= self.cfg.min_elixir:
            return StepResult(True)
        logger.info(
            "Loot low: gold %s / elixir %s below thresholds, continue search",
            gold,
            elixir,
        )
        return StepResult(False, "loot_low")

    def click_next(self) -> StepResult:
        for _ in range(self.cfg.next_max_tries):
            shot = self._capture("next.png")
            if shot is not None:
                match = self._match(shot, "next.png")
                if match.found:
                    self.actions.tap_px(match.cx, match.cy)
                    logger.info("Click Next")
                    self.deps.sleep(1.5)
                    return StepResult(True)
            self.deps.sleep(2)
        return StepResult(False, "next button not found")

    def _drop_group(
        self,
        card_key: str,
        points: list,
        count: int | None = None,
        card_point: list[float] | None = None,
    ) -> None:
        if not points:
            return
        point = card_point if card_point is not None else self.cfg.card_points[card_key]
        self.actions.tap_percent(*point)
        logger.info("Select %s card", card_key)
        self.deps.sleep(0.5)
        taps = len(points) if count is None else max(count, 0)
        for i in range(taps):
            xp, yp = points[i % len(points)]
            self.actions.tap_percent(xp, yp)
            self.deps.sleep(self.cfg.tap_delay_ms / 1000)

    def _drop_heroes(self, chosen) -> None:
        if not self.cfg.hero_cards:
            return
        if not chosen.hero_positions:
            logger.info("Scenario has no hero positions; heroes skipped")
            return
        for i, card in enumerate(self.cfg.hero_cards):
            xp, yp = chosen.hero_positions[i % len(chosen.hero_positions)]
            self.actions.tap_percent(*card)
            logger.info("Deploy hero %d", i + 1)
            self.deps.sleep(0.4)
            self.actions.tap_percent(xp, yp)
            self.deps.sleep(self.cfg.tap_delay_ms / 1000)

    def attack(self) -> StepResult:
        self._state(BotState.ATTACK)
        strategies: list = []
        try:
            strategies = self.deps.load_strategies(self.cfg.strategy_file)
        except Exception as exc:  # noqa: BLE001 - fall back to the legacy drop
            logger.warning("Strategy load failed (%s); using legacy single drop", exc)

        if strategies:
            chosen = random.choice(strategies)
            logger.info("Executing Scenario: %s", chosen.name)
            army = self.cfg.army
            if chosen.wall_wrecker_drop is not None:
                self._drop_group(
                    "wall_wrecker",
                    [chosen.wall_wrecker_drop],
                    count=army.get("wall_wrecker_drop", 1),
                )
            self._drop_group("dragon", chosen.dragon_drops, count=army.get("dragon_drops"))
            self._drop_group(
                "balloon", chosen.balloon_drops, count=army.get("balloon_drops")
            )
            extra_count = army.get("extra_troop", 0)
            if self.cfg.extra_troop_card is not None and extra_count > 0:
                self._drop_group(
                    "extra_troop",
                    chosen.dragon_drops,
                    count=extra_count,
                    card_point=self.cfg.extra_troop_card,
                )
            self._drop_heroes(chosen)
            if self.cfg.rage_card is not None:
                self._drop_group(
                    "rage_spell",
                    chosen.rage_spell_positions,
                    count=army.get("rage_spell"),
                    card_point=self.cfg.rage_card,
                )
            if self.cfg.freeze_card is not None:
                self._drop_group(
                    "freeze_spell",
                    chosen.freeze_spell_positions,
                    count=army.get("freeze_spell"),
                    card_point=self.cfg.freeze_card,
                )
        else:
            logger.info("No strategies loaded; legacy single drop")
            self.actions.tap_percent(*self.cfg.drop_card_point)
            self.deps.sleep(0.5)
            for xp, yp in self.cfg.drop_points:
                self.actions.tap_percent(xp, yp)
                self.deps.sleep(self.cfg.tap_delay_ms / 1000)

        logger.info("Auto end in %d seconds", self.cfg.end_delay_s)
        self.deps.sleep(self.cfg.end_delay_s)
        self.actions.tap_percent(*self.cfg.end_battle_point)
        logger.info("Click End Battle")
        self.deps.sleep(0.2)
        self.actions.tap_percent(*self.cfg.confirm_point)
        logger.info("Confirm End Battle")
        return StepResult(True)

    def return_home(self) -> StepResult:
        self._state(BotState.RETURN_HOME)
        deadline = self.deps.monotonic() + self.cfg.search_timeout_s
        while True:
            shot = self._capture("returnhome.png")
            if shot is None:
                return StepResult(False, "return home capture failed")
            if self._match_safe(shot, "returnhome.png").found or self._match_safe(
                shot, "returnhome_event.png"
            ).found:
                break
            claim = self._match_safe(shot, "claim_reward.png")
            if claim.found:
                return self._claim_event_reward(claim)
            if self.deps.monotonic() > deadline:
                return StepResult(False, "return home timeout")
            self.deps.sleep(10)
        self.actions.tap_percent(*self.cfg.return_home_point)
        logger.info("Tap Return Home")
        self.deps.sleep(8)
        return StepResult(True)

    def _claim_event_reward(self, claim) -> StepResult:
        """Event result screen: Claim Reward -> open chest (4 taps) -> Continue -> home."""
        self.actions.tap_px(claim.cx, claim.cy)
        logger.info("Tap Claim Reward (event chest)")
        self.deps.sleep(2)
        for _ in range(4):
            self.actions.tap_percent(0.5, 0.5)
            self.deps.sleep(1.2)
        logger.info("Chest opened; tapping Continue until home")
        for _ in range(3):
            self.actions.tap_percent(*self.cfg.continue_point)
            self.deps.sleep(3)
            shot = self._capture("event_continue.png")
            if shot is None:
                continue
            if self._match_safe(shot, "attack.png").found:
                logger.info("Back home after event claim")
                return StepResult(True)
        return StepResult(False, "event reward: continue failed")

    def _run_wall_upgrade(self) -> None:
        """Optional wall upgrade after returning home; failures never break the cycle."""
        try:
            result = wallupgrade.run_wall_upgrade(
                self.cfg.wall_upgrade,
                capture=self._capture,
                load_image=self._img,
                find_template=self._match_safe,
                crop_percent=self.deps.crop_percent,
                ocr_boxes=vision.ocr_text_boxes,
                read_gold=lambda crop: self.deps.ocr_digits(
                    vision.enhance_numeric_crop(crop)
                ),
                tap_px=self.actions.tap_px,
                tap_percent=self.actions.tap_percent,
                swipe_percent=self.actions.swipe_percent,
                sleep=self.deps.sleep,
            )
            logger.info(
                "Wall upgrade: %s%s",
                result.status,
                f" ({result.reason})" if result.reason else "",
            )
        except Exception as exc:  # noqa: BLE001 - optional step, never fatal
            logger.warning("Wall upgrade failed: %s", exc)

    # -- cycle -----------------------------------------------------------

    def run_cycle(self) -> StepResult:
        result = self.find_attack()
        if not result.ok:
            return result
        self.actions.tap_px(result.data["px"], result.data["py"])
        logger.info("Click Attack")
        self.deps.sleep(1.0)

        for _ in range(_MAX_LOOT_ROUNDS):
            result = self.matchmaking()
            if not result.ok:
                return result
            result = self.evaluate_loot()
            if result.ok:
                break
            if result.reason != "loot_low":
                return result
            result = self.click_next()
            if not result.ok:
                return result
        else:
            return StepResult(False, "loot loop limit reached")

        result = self.attack()
        if not result.ok:
            return result
        result = self.return_home()
        if result.ok and self.cfg.wall_upgrade.enabled:
            self._run_wall_upgrade()
        return result


def run(config: Config, mode: str, cycles: int, deps: Deps | None = None) -> RunSummary:
    """Run `cycles` full bot cycles. Step-level failures come back as a RunSummary."""
    if deps is None:
        deps = _default_deps(config)
    session = _Session(config, mode, deps)

    result = session.connect()
    if not result.ok:
        return RunSummary(False, 0, result.reason)

    done = 0
    try:
        result = session.prepare()
        if not result.ok:
            return RunSummary(False, 0, result.reason)
        for _ in range(cycles):
            result = session.run_cycle()
            if not result.ok:
                return RunSummary(False, done, result.reason)
            done += 1
    except (AdbError, ValueError, OSError) as exc:
        logger.error("Run aborted: %s", exc)
        return RunSummary(False, done, str(exc))
    session._state(BotState.DONE)
    return RunSummary(True, done, "")
