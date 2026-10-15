"""Attack strategy definitions and loading (original implementation)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class StrategyError(Exception):
    """Raised when a strategy file is invalid."""


@dataclass
class Strategy:
    name: str
    dragon_drops: list[list[float]]
    balloon_drops: list[list[float]]
    wall_wrecker_drop: list[float] | None
    hero_positions: list[list[float]] = field(default_factory=list)
    rage_spell_positions: list[list[float]] = field(default_factory=list)
    freeze_spell_positions: list[list[float]] = field(default_factory=list)


def _point(value: Any, where: str) -> list[float]:
    ok = isinstance(value, (list, tuple)) and len(value) == 2
    if ok:
        ok = all(
            isinstance(v, (int, float))
            and not isinstance(v, bool)
            and 0 <= float(v) <= 1
            for v in value
        )
    if not ok:
        raise StrategyError(f"{where}: expected [x, y] percentages within 0..1")
    return [float(value[0]), float(value[1])]


def _points(value: Any, where: str) -> list[list[float]]:
    if not isinstance(value, (list, tuple)):
        raise StrategyError(f"{where}: expected a list of [x, y] pairs")
    return [_point(p, where) for p in value]


def load_strategies(path: str | Path) -> list[Strategy]:
    """Load strategies from JSON. An absent file returns [] (legacy fallback mode)."""
    strategy_path = Path(path)
    if not strategy_path.is_file():
        return []
    try:
        data = json.loads(strategy_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StrategyError(
            f"{strategy_path}: invalid JSON at line {exc.lineno}: {exc.msg}"
        ) from exc

    raw = data.get("strategies") if isinstance(data, dict) else None
    if not isinstance(raw, list):
        raise StrategyError(f"{strategy_path}: top-level 'strategies' must be a list")

    strategies: list[Strategy] = []
    for index, item in enumerate(raw):
        where = f"strategies[{index}]"
        if not isinstance(item, dict):
            raise StrategyError(f"{where}: expected an object")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            raise StrategyError(f"{where}.name: expected a non-empty string")
        dragon = _points(item.get("dragon_drops", []), f"{where}.dragon_drops")
        balloon = _points(item.get("balloon_drops", []), f"{where}.balloon_drops")
        wrecker_raw = item.get("wall_wrecker_drop")
        wrecker = (
            None
            if wrecker_raw is None
            else _point(wrecker_raw, f"{where}.wall_wrecker_drop")
        )
        if not dragon and not balloon and wrecker is None:
            raise StrategyError(f"{where}: needs at least one drop group")
        hero_positions = _points(
            item.get("hero_positions", []), f"{where}.hero_positions"
        )
        rage_spell_positions = _points(
            item.get("rage_spell_positions", []), f"{where}.rage_spell_positions"
        )
        freeze_spell_positions = _points(
            item.get("freeze_spell_positions", []), f"{where}.freeze_spell_positions"
        )
        strategies.append(
            Strategy(
                name=name.strip(),
                dragon_drops=dragon,
                balloon_drops=balloon,
                wall_wrecker_drop=wrecker,
                hero_positions=hero_positions,
                rage_spell_positions=rage_spell_positions,
                freeze_spell_positions=freeze_spell_positions,
            )
        )
    return strategies
