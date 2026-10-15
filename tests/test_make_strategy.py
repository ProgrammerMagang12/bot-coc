import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

import make_strategy as ms  # noqa: E402

from coclab.strategy import load_strategies  # noqa: E402


def test_points_to_percent():
    assert ms.points_to_percent([(100, 50), (0, 0)], (200, 100)) == [(0.5, 0.5), (0.0, 0.0)]


def test_save_strategy_roundtrip(tmp_path):
    out = tmp_path / "AttackStrategies.json"
    ms.save_strategy(
        "MyStrat",
        dragon=[(0.1, 0.9), (0.2, 0.8)],
        balloon=[(0.3, 0.7)],
        wrecker=(0.4, 0.6),
        out_path=out,
    )
    strategies = load_strategies(out)
    assert len(strategies) == 1
    s = strategies[0]
    assert s.name == "MyStrat"
    assert s.dragon_drops == [[0.1, 0.9], [0.2, 0.8]]
    assert s.balloon_drops == [[0.3, 0.7]]
    assert s.wall_wrecker_drop == [0.4, 0.6]


def test_save_strategy_appends_to_existing(tmp_path):
    out = tmp_path / "AttackStrategies.json"
    ms.save_strategy("A", dragon=[(0.1, 0.1)], balloon=[], wrecker=None, out_path=out)
    ms.save_strategy("B", dragon=[(0.2, 0.2)], balloon=[], wrecker=None, out_path=out)
    assert [s.name for s in load_strategies(out)] == ["A", "B"]
