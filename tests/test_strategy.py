import json
import random

import pytest

from coclab.strategy import (
    Strategy,
    StrategyError,
    jitter_point,
    load_strategies,
    mirror_strategy,
)


def _write(tmp_path, data):
    p = tmp_path / "s.json"
    p.write_text(json.dumps(data))
    return p


def test_load_valid_strategies(tmp_path):
    p = _write(
        tmp_path,
        {
            "strategies": [
                {
                    "name": "A",
                    "dragon_drops": [[0.1, 0.2], [0.3, 0.4]],
                    "balloon_drops": [[0.5, 0.6]],
                    "wall_wrecker_drop": [0.2, 0.3],
                },
                {"name": "B", "dragon_drops": [[0.1, 0.1]]},
            ]
        },
    )
    strategies = load_strategies(p)
    assert [s.name for s in strategies] == ["A", "B"]
    assert isinstance(strategies[0], Strategy)
    assert strategies[0].dragon_drops == [[0.1, 0.2], [0.3, 0.4]]
    assert strategies[0].wall_wrecker_drop == [0.2, 0.3]
    assert strategies[1].balloon_drops == []
    assert strategies[1].wall_wrecker_drop is None


def test_missing_file_returns_empty_list(tmp_path):
    assert load_strategies(tmp_path / "nope.json") == []


def test_empty_name_rejected(tmp_path):
    p = _write(tmp_path, {"strategies": [{"name": " ", "dragon_drops": [[0.1, 0.1]]}]})
    with pytest.raises(StrategyError, match="name"):
        load_strategies(p)


def test_point_out_of_range_rejected(tmp_path):
    p = _write(tmp_path, {"strategies": [{"name": "A", "dragon_drops": [[1.5, 0.1]]}]})
    with pytest.raises(StrategyError, match="dragon_drops"):
        load_strategies(p)


def test_all_groups_empty_rejected(tmp_path):
    p = _write(tmp_path, {"strategies": [{"name": "A"}]})
    with pytest.raises(StrategyError, match="at least one"):
        load_strategies(p)


def test_optional_hero_and_spell_positions_parsed(tmp_path):
    p = _write(
        tmp_path,
        {
            "strategies": [
                {
                    "name": "A",
                    "dragon_drops": [[0.1, 0.1]],
                    "hero_positions": [[0.2, 0.2]],
                    "rage_spell_positions": [[0.3, 0.3]],
                    "freeze_spell_positions": [[0.4, 0.4]],
                }
            ]
        },
    )
    s = load_strategies(p)[0]
    assert s.hero_positions == [[0.2, 0.2]]
    assert s.rage_spell_positions == [[0.3, 0.3]]
    assert s.freeze_spell_positions == [[0.4, 0.4]]


def test_optional_positions_default_empty(tmp_path):
    p = _write(tmp_path, {"strategies": [{"name": "A", "dragon_drops": [[0.1, 0.1]]}]})
    s = load_strategies(p)[0]
    assert s.hero_positions == []
    assert s.rage_spell_positions == []
    assert s.freeze_spell_positions == []


def test_jitter_point_zero_returns_same():
    assert jitter_point(0.3, 0.4, 0.0, 0.0) == [0.3, 0.4]


def test_jitter_point_direction_toward_center():
    rng = random.Random(1)
    right = jitter_point(0.2, 0.5, 0.03, 0.03, rng=rng)
    assert right[0] >= 0.2 and right[1] <= 0.5
    left = jitter_point(0.8, 0.5, 0.03, 0.03, rng=rng)
    assert left[0] <= 0.8 and left[1] <= 0.5


def test_jitter_point_clamped_at_edges():
    rng = random.Random(2)
    for _ in range(200):
        x, y = jitter_point(0.021, 0.031, 0.03, 0.03, rng=rng)
        assert 0.02 <= x <= 0.98 and 0.03 <= y <= 0.80


def test_jitter_point_clamped_at_upper_edges():
    """Titik di dekat tepi atas tetap dijepit ke batas 0.98/0.80."""
    rng = random.Random(2)
    for _ in range(200):
        x, y = jitter_point(0.979, 0.799, 0.03, 0.03, rng=rng)
        assert 0.02 <= x <= 0.98 and 0.03 <= y <= 0.80
    # nilai awal di atas batas → clamp atas harus berlaku (xp>0.5 → delta negatif)
    x, y = jitter_point(0.99, 0.81, 0.1, 0.1, rng=random.Random(3))
    assert x <= 0.98 and y <= 0.80


def test_mirror_strategy_flips_all_points():
    s = Strategy(
        name="a", dragon_drops=[[0.1, 0.4]], balloon_drops=[[0.2, 0.3]],
        wall_wrecker_drop=[0.3, 0.35], hero_positions=[[0.4, 0.5]],
        rage_spell_positions=[[0.15, 0.2]], freeze_spell_positions=[[0.25, 0.25]],
    )
    m = mirror_strategy(s)
    assert m.name == "a" and m.dragon_drops == [[0.9, 0.4]]
    assert m.balloon_drops == [[0.8, 0.3]] and m.wall_wrecker_drop == [0.7, 0.35]
    assert m.hero_positions == [[0.6, 0.5]]
    assert m.rage_spell_positions == [[0.85, 0.2]]
    assert m.freeze_spell_positions == [[0.75, 0.25]]


def test_mirror_strategy_none_wrecker_kept_none():
    s = Strategy(name="b", dragon_drops=[[0.1, 0.4]], balloon_drops=[], wall_wrecker_drop=None)
    assert mirror_strategy(s).wall_wrecker_drop is None
