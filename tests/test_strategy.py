import json

import pytest

from coclab.strategy import Strategy, StrategyError, load_strategies


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
