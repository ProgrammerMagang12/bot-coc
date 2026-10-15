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
        wall_upgrade=wall_upgrade,
    )
