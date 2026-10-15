import json

import pytest

from pathlib import Path

from coclab.config import load_config, Config, ConfigError

EXAMPLE = Path(__file__).parent.parent / "config.example.json"


def test_example_config_loads():
    cfg = load_config(EXAMPLE)
    assert isinstance(cfg, Config)
    assert cfg.device_address == "127.0.0.1:5555"
    assert 0 < cfg.threshold <= 1
    assert cfg.on_ocr_fail in ("stop", "attack")


def test_missing_file_names_example(tmp_path):
    with pytest.raises(ConfigError, match="config.example.json"):
        load_config(tmp_path / "nope.json")


def test_invalid_threshold_rejected(tmp_path):
    data = json.loads(EXAMPLE.read_text())
    data["threshold"] = 1.5
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    with pytest.raises(ConfigError, match="threshold"):
        load_config(p)


def test_loot_roi_must_be_ordered(tmp_path):
    data = json.loads(EXAMPLE.read_text())
    data["loot_roi"] = [0.5, 0.1, 0.2, 0.9]  # x2 < x1
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    with pytest.raises(ConfigError, match="loot_roi"):
        load_config(p)


def test_example_config_matches_spec_defaults():
    cfg = load_config(EXAMPLE)
    assert cfg.threshold == 0.69
    assert cfg.end_delay_s == 20
    assert cfg.next_max_tries == 5
    assert cfg.search_timeout_s == 60


def test_example_config_loot_settle():
    cfg = load_config(EXAMPLE)
    assert cfg.loot_settle_s == 1.5


def test_example_config_drop_card_point():
    cfg = load_config(EXAMPLE)
    assert cfg.drop_card_point == [0.251, 0.933]


def test_invalid_drop_card_point_rejected(tmp_path):
    data = json.loads(EXAMPLE.read_text())
    data["drop_card_point"] = [1.5, 0.5]
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    with pytest.raises(ConfigError, match="drop_card_point"):
        load_config(p)


def test_invalid_loot_settle_rejected(tmp_path):
    data = json.loads(EXAMPLE.read_text())
    data["loot_settle_s"] = -1
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    with pytest.raises(ConfigError, match="loot_settle_s"):
        load_config(p)


def test_example_config_v2_fields():
    cfg = load_config(EXAMPLE)
    assert cfg.strategy_file == "AttackStrategies.json"
    assert set(cfg.card_points) >= {"dragon", "balloon", "wall_wrecker"}
    assert cfg.wall_upgrade.enabled is False
    assert cfg.wall_upgrade.gold_min == 2000000


def test_invalid_wall_gold_min_rejected(tmp_path):
    data = json.loads(EXAMPLE.read_text())
    data["wall_upgrade"]["gold_min"] = -5
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    with pytest.raises(ConfigError, match="gold_min"):
        load_config(p)


def test_missing_card_point_key_rejected(tmp_path):
    data = json.loads(EXAMPLE.read_text())
    del data["card_points"]["balloon"]
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    with pytest.raises(ConfigError, match="balloon"):
        load_config(p)
