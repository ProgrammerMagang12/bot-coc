"""Convert a CROWZ-format strategy file to coc-lab format.

Reads {"Strategies": [{Name, DragonDrops, BalloonDrops, WallWreckerDrop,
HeroPositions, RageSpellPositions, FreezeSpellPositions}, ...]} and writes
{"strategies": [{name, dragon_drops, balloon_drops, wall_wrecker_drop,
hero_positions, rage_spell_positions, freeze_spell_positions}, ...]}.

Usage:
    py tools/import_crowz_strategies.py --input path/AttackStrategies.json [--out AttackStrategies.json] [--append]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _get(data: dict, *keys):
    lowered = {str(k).lower(): v for k, v in data.items()}
    for key in keys:
        if key.lower() in lowered:
            return lowered[key.lower()]
    raise KeyError(f"missing key: {keys[0]}")


def _get_or_none(data: dict, *keys):
    try:
        return _get(data, *keys)
    except KeyError:
        return None


def _points(value) -> list[list[float]]:
    return [[float(p[0]), float(p[1])] for p in (value or [])]


def _point_or_none(value) -> list[float] | None:
    return [float(value[0]), float(value[1])] if value else None


def convert(input_path: str | Path, out_path: str | Path, append: bool = False) -> int:
    src = Path(input_path)
    data = json.loads(src.read_text(encoding="utf-8"))
    strategies = data.get("Strategies") or data.get("strategies")
    if not isinstance(strategies, list):
        raise ValueError(f"{src}: no 'Strategies' list found")

    converted = []
    for item in strategies:
        converted.append(
            {
                "name": str(_get(item, "Name", "name")).strip(),
                "dragon_drops": _points(_get(item, "DragonDrops", "dragon_drops")),
                "balloon_drops": _points(_get(item, "BalloonDrops", "balloon_drops")),
                "wall_wrecker_drop": _point_or_none(
                    _get_or_none(item, "WallWreckerDrop", "wall_wrecker_drop")
                ),
                "hero_positions": _points(
                    _get_or_none(item, "HeroPositions", "hero_positions")
                ),
                "rage_spell_positions": _points(
                    _get_or_none(item, "RageSpellPositions", "rage_spell_positions")
                ),
                "freeze_spell_positions": _points(
                    _get_or_none(item, "FreezeSpellPositions", "freeze_spell_positions")
                ),
            }
        )

    out = Path(out_path)
    payload: dict = {"strategies": []}
    if append and out.is_file():
        payload = json.loads(out.read_text(encoding="utf-8"))
        payload.setdefault("strategies", [])
    payload["strategies"].extend(converted)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return len(converted)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="import_crowz_strategies")
    parser.add_argument("--input", required=True, help="CROWZ-format strategy json")
    parser.add_argument("--out", default="AttackStrategies.json")
    parser.add_argument("--append", action="store_true")
    args = parser.parse_args(argv)
    count = convert(args.input, args.out, append=args.append)
    print(f"imported {count} strategy(ies) to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
