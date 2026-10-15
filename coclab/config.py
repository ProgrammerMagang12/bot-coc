"""Configuration loading and validation for coc-lab."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    """Raised when a config file is missing or invalid."""


@dataclass
class Config:
    adb_path: str
    device_address: str
    threshold: float
    min_resource: int
    loot_roi: list[float]
    on_ocr_fail: str
    drop_points: list[list[float]]
    tap_delay_ms: int
    end_delay_s: int
    end_battle_point: list[float]
    confirm_point: list[float]
    return_home_point: list[float]
    next_max_tries: int
    search_timeout_s: int
    workdir: str
    assets_dir: str


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


def _positive_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigError(f"{field}: expected a positive integer")
    return value


def _nonempty_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{field}: expected a non-empty string")
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

    roi = _require(data, "loot_roi")
    if not isinstance(roi, (list, tuple)) or len(roi) != 4:
        raise ConfigError("loot_roi: expected [x1, y1, x2, y2]")
    x1, y1, x2, y2 = (_percent_value(v, "loot_roi") for v in roi)
    if not (x1 < x2 and y1 < y2):
        raise ConfigError(f"loot_roi: x1<x2 and y1<y2 required (got {list(roi)})")

    drop_raw = _require(data, "drop_points")
    if not isinstance(drop_raw, (list, tuple)) or not drop_raw:
        raise ConfigError("drop_points: expected a non-empty list of [x, y] pairs")

    on_ocr_fail = _require(data, "on_ocr_fail")
    if on_ocr_fail not in ("stop", "attack"):
        raise ConfigError("on_ocr_fail: expected 'stop' or 'attack'")

    return Config(
        adb_path=_nonempty_str(_require(data, "adb_path"), "adb_path"),
        device_address=_nonempty_str(_require(data, "device_address"), "device_address"),
        threshold=float(threshold),
        min_resource=_positive_int(_require(data, "min_resource"), "min_resource"),
        loot_roi=[x1, y1, x2, y2],
        on_ocr_fail=on_ocr_fail,
        drop_points=[_point(pair, "drop_points") for pair in drop_raw],
        tap_delay_ms=_positive_int(_require(data, "tap_delay_ms"), "tap_delay_ms"),
        end_delay_s=_positive_int(_require(data, "end_delay_s"), "end_delay_s"),
        end_battle_point=_point(_require(data, "end_battle_point"), "end_battle_point"),
        confirm_point=_point(_require(data, "confirm_point"), "confirm_point"),
        return_home_point=_point(_require(data, "return_home_point"), "return_home_point"),
        next_max_tries=_positive_int(_require(data, "next_max_tries"), "next_max_tries"),
        search_timeout_s=_positive_int(_require(data, "search_timeout_s"), "search_timeout_s"),
        workdir=_nonempty_str(_require(data, "workdir"), "workdir"),
        assets_dir=_nonempty_str(_require(data, "assets_dir"), "assets_dir"),
    )
