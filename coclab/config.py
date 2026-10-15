"""Configuration loading and validation for coc-lab."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    """Raised when a config file is missing or invalid."""


@dataclass
class WallUpgradeConfig:
    enabled: bool
    gold_min: int
    gold_storage_roi: list[float]
    upgrade_logo: str
    wall_text_roi: list[float]
    gold_upgrade_point: list[float]
    gold_confirm_point: list[float]
    elixir_upgrade_point: list[float]
    elixir_confirm_point: list[float]
    max_scroll_tries: int


@dataclass
class Config:
    adb_path: str
    device_address: str
    threshold: float
    min_gold: int
    min_elixir: int
    loot_roi: list[float]
    loot_roi_elixir: list[float]
    on_ocr_fail: str
    drop_card_point: list[float]
    drop_points: list[list[float]]
    drag_deploy_ms: int
    tap_delay_ms: int
    end_delay_s: int
    end_battle_point: list[float]
    confirm_point: list[float]
    return_home_point: list[float]
    next_max_tries: int
    search_timeout_s: int
    workdir: str
    assets_dir: str
    loot_settle_s: float
    strategy_file: str
    card_points: dict[str, list[float]]
    hero_cards: list[list[float]]
    extra_troop_card: list[float] | None
    continue_point: list[float]
    star_bonus_point: list[float]
    notifications_not_now_point: list[float]
    speed_up_point: list[float]
    speed_up_taps: int
    min_dark: int
    loot_roi_dark: list[float]
    reload_game_point: list[float]
    reload_game_cluster: list[list[float]]
    hero_skill_points: list[list[float]]
    hero_skill_delays_s: list[int]
    find_attack_timeout_s: int
    emulator_path: str
    emulator_args: list[str]
    de_roi: list[float]
    de_full_value: int
    army_badge_roi: list[float]
    coc_package: str
    collect_points: list[list[float]]
    train_points: list[list[float]]
    train_wait_s: int
    train_ui: dict
    train_mode: str
    rage_card: list[float] | None
    freeze_card: list[float] | None
    card_detection: bool
    card_threshold: float
    extra_troop_template: str | None
    deck_strict_types: list[str]
    deploy_jitter_px: int
    mirror_strategies: bool
    tap_delay_jitter_pct: int
    another_device_wait_s: int
    connection_lost_point: list[float] | None
    zoom_out_enabled: bool
    zoom_out_pinches: int
    zoom_out_settle_s: float
    army: dict[str, int]
    wall_upgrade: WallUpgradeConfig


def _require(data: dict[str, Any], key: str) -> Any:
    if key not in data:
        raise ConfigError(f"missing field '{key}'")
    return data[key]


def _percent_value(value: Any, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ConfigError(f"{field}: expected a number between 0 and 1")
    result = float(value)
    if not 0.0 <= result <= 1.0:
        raise ConfigError(f"{field}: value {result} outside 0..1")
    return result


def _point(value: Any, field: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ConfigError(f"{field}: expected an [x, y] percent pair")
    return [_percent_value(value[0], field), _percent_value(value[1], field)]


def _roi(value: Any, field: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ConfigError(f"{field}: expected [x1, y1, x2, y2]")
    x1, y1, x2, y2 = (_percent_value(v, field) for v in value)
    if not (x1 < x2 and y1 < y2):
        raise ConfigError(f"{field}: x1<x2 and y1<y2 required (got {list(value)})")
    return [x1, y1, x2, y2]


def _positive_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigError(f"{field}: expected a positive integer")
    return value


def _nonneg_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ConfigError(f"{field}: expected a non-negative integer")
    return value


def _nonneg_number(value: Any, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
        raise ConfigError(f"{field}: expected a number >= 0")
    return float(value)


def _nonempty_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{field}: expected a non-empty string")
    return value


def _bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ConfigError(f"{field}: expected true or false")
    return value


def load_config(path: str | Path) -> Config:
    """Load and validate a config file. Raises ConfigError with the offending field."""
    config_path = Path(path)
    if not config_path.is_file():
        raise ConfigError(
            f"config file not found: {config_path}. "
            "Copy config.example.json to config.json and adjust it."
        )

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{config_path}: invalid JSON at line {exc.lineno}: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{config_path}: top-level JSON value must be an object")

    threshold = _require(data, "threshold")
    if (
        not isinstance(threshold, (int, float))
        or isinstance(threshold, bool)
        or not 0 < float(threshold) <= 1
    ):
        raise ConfigError("threshold: expected a number greater than 0 and at most 1")

    loot_roi = _roi(_require(data, "loot_roi"), "loot_roi")
    loot_roi_elixir = _roi(_require(data, "loot_roi_elixir"), "loot_roi_elixir")

    drop_raw = _require(data, "drop_points")
    if not isinstance(drop_raw, (list, tuple)) or not drop_raw:
        raise ConfigError("drop_points: expected a non-empty list of [x, y] pairs")

    on_ocr_fail = _require(data, "on_ocr_fail")
    if on_ocr_fail not in ("stop", "next", "attack"):
        raise ConfigError("on_ocr_fail: expected 'stop', 'next' or 'attack'")

    card_raw = _require(data, "card_points")
    if not isinstance(card_raw, dict):
        raise ConfigError("card_points: expected an object")
    card_points: dict[str, list[float]] = {}
    for key in ("dragon", "balloon", "wall_wrecker"):
        if key not in card_raw:
            raise ConfigError(f"card_points.{key}: missing")
        card_points[key] = _point(card_raw[key], f"card_points.{key}")

    wall_raw = _require(data, "wall_upgrade")
    if not isinstance(wall_raw, dict):
        raise ConfigError("wall_upgrade: expected an object")
    wall_upgrade = WallUpgradeConfig(
        enabled=_bool(_require(wall_raw, "enabled"), "wall_upgrade.enabled"),
        gold_min=_positive_int(_require(wall_raw, "gold_min"), "wall_upgrade.gold_min"),
        gold_storage_roi=_roi(
            _require(wall_raw, "gold_storage_roi"), "wall_upgrade.gold_storage_roi"
        ),
        upgrade_logo=_nonempty_str(
            _require(wall_raw, "upgrade_logo"), "wall_upgrade.upgrade_logo"
        ),
        wall_text_roi=_roi(_require(wall_raw, "wall_text_roi"), "wall_upgrade.wall_text_roi"),
        gold_upgrade_point=_point(
            _require(wall_raw, "gold_upgrade_point"), "wall_upgrade.gold_upgrade_point"
        ),
        gold_confirm_point=_point(
            _require(wall_raw, "gold_confirm_point"), "wall_upgrade.gold_confirm_point"
        ),
        elixir_upgrade_point=_point(
            _require(wall_raw, "elixir_upgrade_point"), "wall_upgrade.elixir_upgrade_point"
        ),
        elixir_confirm_point=_point(
            _require(wall_raw, "elixir_confirm_point"), "wall_upgrade.elixir_confirm_point"
        ),
        max_scroll_tries=_positive_int(
            _require(wall_raw, "max_scroll_tries"), "wall_upgrade.max_scroll_tries"
        ),
    )

    hero_raw = data.get("hero_cards", [])
    if not isinstance(hero_raw, list):
        raise ConfigError("hero_cards: expected a list of [x, y] pairs")
    hero_cards = [_point(pair, f"hero_cards[{i}]") for i, pair in enumerate(hero_raw)]

    extra_raw = data.get("extra_troop_card")
    extra_troop_card = None if extra_raw is None else _point(extra_raw, "extra_troop_card")

    continue_point = _point(data.get("continue_point", [0.51, 0.90]), "continue_point")
    star_bonus_point = _point(
        data.get("star_bonus_point", [0.495, 0.82]), "star_bonus_point"
    )
    notifications_not_now_point = _point(
        data.get("notifications_not_now_point", [0.38, 0.68]),
        "notifications_not_now_point",
    )
    speed_up_point = _point(data.get("speed_up_point", [0.959, 0.572]), "speed_up_point")
    speed_up_taps = _nonneg_int(data.get("speed_up_taps", 2), "speed_up_taps")
    min_dark = _nonneg_int(data.get("min_dark", 0), "min_dark")
    loot_roi_dark = _roi(
        data.get("loot_roi_dark", [0.050, 0.222, 0.183, 0.278]), "loot_roi_dark"
    )
    reload_game_point = _point(
        data.get("reload_game_point", [0.309, 0.591]), "reload_game_point"
    )
    cluster_raw = data.get(
        "reload_game_cluster", [[0.28, 0.59], [0.31, 0.59], [0.34, 0.59]]
    )
    if not isinstance(cluster_raw, list):
        raise ConfigError("reload_game_cluster: expected a list of [x, y] pairs")
    reload_game_cluster = [
        _point(pair, f"reload_game_cluster[{i}]") for i, pair in enumerate(cluster_raw)
    ]
    skill_raw = data.get("hero_skill_points", [])
    if not isinstance(skill_raw, list):
        raise ConfigError("hero_skill_points: expected a list of [x, y] pairs")
    hero_skill_points = [
        _point(pair, f"hero_skill_points[{i}]") for i, pair in enumerate(skill_raw)
    ]
    delays_raw = data.get("hero_skill_delays_s", [5, 10, 15, 20, 30, 45, 60])
    if not isinstance(delays_raw, list):
        raise ConfigError("hero_skill_delays_s: expected a list of seconds")
    hero_skill_delays_s = [
        _nonneg_int(value, f"hero_skill_delays_s[{i}]")
        for i, value in enumerate(delays_raw)
    ]
    find_attack_timeout_s = _positive_int(
        data.get("find_attack_timeout_s", 60), "find_attack_timeout_s"
    )
    emulator_path = str(data.get("emulator_path", ""))
    args_raw = data.get("emulator_args", ["launch", "--index", "0"])
    if not isinstance(args_raw, list) or not all(isinstance(a, str) for a in args_raw):
        raise ConfigError("emulator_args: expected a list of strings")
    emulator_args = list(args_raw)
    de_roi = _roi(data.get("de_roi", [0.880, 0.168, 0.960, 0.212]), "de_roi")
    de_full_value = _nonneg_int(data.get("de_full_value", 0), "de_full_value")
    army_badge_roi = _roi(data.get("army_badge_roi", [0.070, 0.835, 0.140, 0.895]), "army_badge_roi")
    coc_package = _nonempty_str(
        data.get("coc_package", "com.supercell.clashofclans"), "coc_package"
    )
    collect_raw = data.get("collect_points", [])
    if not isinstance(collect_raw, list):
        raise ConfigError("collect_points: expected a list of [x, y] pairs")
    collect_points = [
        _point(pair, f"collect_points[{i}]") for i, pair in enumerate(collect_raw)
    ]
    train_raw = data.get("train_points", [])
    if not isinstance(train_raw, list):
        raise ConfigError("train_points: expected a list of [x, y] pairs")
    train_points = [
        _point(pair, f"train_points[{i}]") for i, pair in enumerate(train_raw)
    ]
    train_wait_s = _nonneg_int(data.get("train_wait_s", 5), "train_wait_s")
    ui_raw = data.get("train_ui", {})
    if not isinstance(ui_raw, dict):
        raise ConfigError("train_ui: expected an object")
    train_ui: dict = {}
    for key, value in ui_raw.items():
        if value is None:
            continue
        if key == "grid":
            if not isinstance(value, dict):
                raise ConfigError("train_ui.grid: expected an object")
            train_ui["grid"] = {
                group: _point(point, f"train_ui.grid.{group}")
                for group, point in value.items()
            }
        else:
            train_ui[key] = _point(value, f"train_ui.{key}")
    train_mode = str(data.get("train_mode", "quick_train"))
    if train_mode not in ("quick_train", "build"):
        raise ConfigError("train_mode: expected 'quick_train' or 'build'")

    rage_raw = data.get("rage_card")
    rage_card = None if rage_raw is None else _point(rage_raw, "rage_card")
    freeze_raw = data.get("freeze_card")
    freeze_card = None if freeze_raw is None else _point(freeze_raw, "freeze_card")

    card_detection = _bool(data.get("card_detection", True), "card_detection")
    threshold_raw = data.get("card_threshold", 0.55)
    if (
        not isinstance(threshold_raw, (int, float))
        or isinstance(threshold_raw, bool)
        or not 0 < float(threshold_raw) <= 1
    ):
        raise ConfigError(
            "card_threshold: expected a number greater than 0 and at most 1"
        )
    card_threshold = float(threshold_raw)
    extra_tpl_raw = data.get("extra_troop_template")
    extra_troop_template = (
        None
        if extra_tpl_raw is None
        else _nonempty_str(extra_tpl_raw, "extra_troop_template")
    )

    strict_raw = data.get("deck_strict_types", ["dragon", "balloon", "extra", "rage", "freeze"])
    if not isinstance(strict_raw, list) or not all(
        isinstance(v, str) and v.strip() for v in strict_raw
    ):
        raise ConfigError("deck_strict_types: expected a list of strings")
    deck_strict_types = [str(v).strip() for v in strict_raw]
    deploy_jitter_px = _nonneg_int(data.get("deploy_jitter_px", 38), "deploy_jitter_px")
    mirror_strategies = _bool(data.get("mirror_strategies", True), "mirror_strategies")
    pct_raw = data.get("tap_delay_jitter_pct", 30)
    if not isinstance(pct_raw, int) or isinstance(pct_raw, bool) or not 0 <= pct_raw <= 90:
        raise ConfigError("tap_delay_jitter_pct: expected an integer between 0 and 90")
    tap_delay_jitter_pct = int(pct_raw)
    another_device_wait_s = _positive_int(
        data.get("another_device_wait_s", 30), "another_device_wait_s"
    )
    lost_raw = data.get("connection_lost_point")
    connection_lost_point = None if lost_raw is None else _point(lost_raw, "connection_lost_point")

    zoom_out_enabled = _bool(data.get("zoom_out_enabled", True), "zoom_out_enabled")
    pinches_raw = data.get("zoom_out_pinches", 3)
    if (
        not isinstance(pinches_raw, int)
        or isinstance(pinches_raw, bool)
        or not 0 <= pinches_raw <= 10
    ):
        raise ConfigError("zoom_out_pinches: expected an integer between 0 and 10")
    zoom_out_pinches = int(pinches_raw)
    zoom_out_settle_s = _nonneg_number(
        data.get("zoom_out_settle_s", 0.8), "zoom_out_settle_s"
    )

    army_raw = data.get("army", {})
    if not isinstance(army_raw, dict):
        raise ConfigError("army: expected an object of troop counts")
    army = {key: _positive_int(value, f"army.{key}") for key, value in army_raw.items()}

    return Config(
        adb_path=_nonempty_str(_require(data, "adb_path"), "adb_path"),
        device_address=_nonempty_str(_require(data, "device_address"), "device_address"),
        threshold=float(threshold),
        min_gold=_positive_int(_require(data, "min_gold"), "min_gold"),
        min_elixir=_positive_int(_require(data, "min_elixir"), "min_elixir"),
        loot_roi=loot_roi,
        loot_roi_elixir=loot_roi_elixir,
        on_ocr_fail=on_ocr_fail,
        drop_card_point=_point(_require(data, "drop_card_point"), "drop_card_point"),
        drop_points=[_point(pair, "drop_points") for pair in drop_raw],
        drag_deploy_ms=_positive_int(_require(data, "drag_deploy_ms"), "drag_deploy_ms"),
        tap_delay_ms=_positive_int(_require(data, "tap_delay_ms"), "tap_delay_ms"),
        end_delay_s=_positive_int(_require(data, "end_delay_s"), "end_delay_s"),
        end_battle_point=_point(_require(data, "end_battle_point"), "end_battle_point"),
        confirm_point=_point(_require(data, "confirm_point"), "confirm_point"),
        return_home_point=_point(_require(data, "return_home_point"), "return_home_point"),
        next_max_tries=_positive_int(_require(data, "next_max_tries"), "next_max_tries"),
        search_timeout_s=_positive_int(_require(data, "search_timeout_s"), "search_timeout_s"),
        workdir=_nonempty_str(_require(data, "workdir"), "workdir"),
        assets_dir=_nonempty_str(_require(data, "assets_dir"), "assets_dir"),
        loot_settle_s=_nonneg_number(_require(data, "loot_settle_s"), "loot_settle_s"),
        strategy_file=_nonempty_str(_require(data, "strategy_file"), "strategy_file"),
        card_points=card_points,
        hero_cards=hero_cards,
        extra_troop_card=extra_troop_card,
        continue_point=continue_point,
        star_bonus_point=star_bonus_point,
        notifications_not_now_point=notifications_not_now_point,
        speed_up_point=speed_up_point,
        speed_up_taps=speed_up_taps,
        min_dark=min_dark,
        loot_roi_dark=loot_roi_dark,
        reload_game_point=reload_game_point,
        reload_game_cluster=reload_game_cluster,
        hero_skill_points=hero_skill_points,
        hero_skill_delays_s=hero_skill_delays_s,
        find_attack_timeout_s=find_attack_timeout_s,
        emulator_path=emulator_path,
        emulator_args=emulator_args,
        de_roi=de_roi,
        de_full_value=de_full_value,
        army_badge_roi=army_badge_roi,
        coc_package=coc_package,
        collect_points=collect_points,
        train_points=train_points,
        train_wait_s=train_wait_s,
        train_ui=train_ui,
        train_mode=train_mode,
        rage_card=rage_card,
        freeze_card=freeze_card,
        card_detection=card_detection,
        card_threshold=card_threshold,
        extra_troop_template=extra_troop_template,
        deck_strict_types=deck_strict_types,
        deploy_jitter_px=deploy_jitter_px,
        mirror_strategies=mirror_strategies,
        tap_delay_jitter_pct=tap_delay_jitter_pct,
        another_device_wait_s=another_device_wait_s,
        connection_lost_point=connection_lost_point,
        zoom_out_enabled=zoom_out_enabled,
        zoom_out_pinches=zoom_out_pinches,
        zoom_out_settle_s=zoom_out_settle_s,
        army=army,
        wall_upgrade=wall_upgrade,
    )
