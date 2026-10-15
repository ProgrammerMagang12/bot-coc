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
    assert cfg.on_ocr_fail in ("stop", "next", "attack")


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
    assert cfg.end_delay_s == 150
    assert cfg.next_max_tries == 5
    assert cfg.search_timeout_s == 60


def test_example_config_loot_settle():
    cfg = load_config(EXAMPLE)
    assert cfg.loot_settle_s == 3


def test_example_config_drop_card_point():
    cfg = load_config(EXAMPLE)
    assert cfg.drop_card_point == [0.091, 0.933]


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


def test_example_config_drag_deploy_ms():
    cfg = load_config(EXAMPLE)
    assert cfg.drag_deploy_ms == 800


def test_invalid_drag_deploy_rejected(tmp_path):
    data = json.loads(EXAMPLE.read_text())
    data["drag_deploy_ms"] = 0
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    with pytest.raises(ConfigError, match="drag_deploy_ms"):
        load_config(p)


def test_example_config_dual_thresholds():
    cfg = load_config(EXAMPLE)
    assert cfg.min_gold == 500000
    assert cfg.min_elixir == 500000
    assert cfg.loot_roi_elixir == [0.050, 0.165, 0.183, 0.222]


def test_invalid_min_elixir_rejected(tmp_path):
    data = json.loads(EXAMPLE.read_text())
    data["min_elixir"] = -1
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    with pytest.raises(ConfigError, match="min_elixir"):
        load_config(p)


def test_example_config_deploy_and_event_fields():
    cfg = load_config(EXAMPLE)
    assert cfg.hero_cards == [[0.424, 0.91], [0.502, 0.91]]
    assert cfg.extra_troop_card == [0.24, 0.933]
    assert cfg.rage_card == [0.58, 0.933]
    assert cfg.freeze_card == [0.658, 0.933]
    assert cfg.continue_point == [0.51, 0.90]
    assert cfg.star_bonus_point == [0.495, 0.82]
    assert cfg.notifications_not_now_point == [0.38, 0.68]
    assert cfg.speed_up_point == [0.959, 0.572]
    assert cfg.speed_up_taps == 2
    assert cfg.min_dark == 0
    assert cfg.loot_roi_dark == [0.050, 0.222, 0.183, 0.278]
    assert cfg.reload_game_point == [0.309, 0.591]
    assert cfg.hero_skill_points == [[0.404, 0.76], [0.445, 0.76]]
    assert cfg.hero_skill_delays_s == [5, 10, 15, 20, 30, 45, 60]
    assert cfg.find_attack_timeout_s == 60
    assert cfg.emulator_path == ""
    assert cfg.emulator_args == ["launch", "--index", "0"]
    assert cfg.de_roi == [0.880, 0.168, 0.960, 0.212]
    assert cfg.de_full_value == 0
    assert cfg.coc_package == "com.supercell.clashofclans"
    assert cfg.collect_points == []
    assert cfg.train_points == []
    assert cfg.train_wait_s == 5
    assert cfg.army == {
        "dragon_drops": 13,
        "balloon_drops": 18,
        "wall_wrecker_drop": 1,
        "extra_troop": 2,
        "rage_spell": 4,
        "freeze_spell": 3,
    }


def test_config_parses_train_ui(tmp_path):
    import json

    data = json.loads(EXAMPLE.read_text())
    data["train_ui"] = {
        "army_button": [0.05, 0.7],
        "clear_troops": [0.9, 0.2],
        "grid": {"dragon_drops": [0.4, 0.6]},
        "close_button": [0.95, 0.05],
    }
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    cfg = load_config(p)
    assert cfg.train_ui["army_button"] == [0.05, 0.7]
    assert cfg.train_ui["grid"]["dragon_drops"] == [0.4, 0.6]


def test_example_config_train_mode_default():
    cfg = load_config(EXAMPLE)
    assert cfg.train_mode == "quick_train"


def test_invalid_train_mode_rejected(tmp_path):
    data = json.loads(EXAMPLE.read_text())
    data["train_mode"] = "xyz"
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    with pytest.raises(ConfigError, match="train_mode"):
        load_config(p)


def test_invalid_hero_card_rejected(tmp_path):
    data = json.loads(EXAMPLE.read_text())
    data["hero_cards"] = [[1.5, 0.5]]
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    with pytest.raises(ConfigError, match="hero_cards"):
        load_config(p)


def test_invalid_army_count_rejected(tmp_path):
    data = json.loads(EXAMPLE.read_text())
    data["army"]["extra_troop"] = 0
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    with pytest.raises(ConfigError, match="army.extra_troop"):
        load_config(p)


def test_example_config_reliability_fields():
    cfg = load_config(EXAMPLE)
    assert cfg.deck_strict_types == ["dragon", "balloon", "extra", "rage", "freeze"]
    assert cfg.deploy_jitter_px == 38
    assert cfg.mirror_strategies is True
    assert cfg.tap_delay_jitter_pct == 30
    assert cfg.another_device_wait_s == 30
    assert cfg.connection_lost_point is None


def test_deck_strict_types_normalized_lowercase(tmp_path):
    """Entri uppercase/spasi dinormalkan agar 'Dragon' tak jadi tipe tak dikenal."""
    data = json.loads(EXAMPLE.read_text())
    data["deck_strict_types"] = ["Dragon", " balloon "]
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    cfg = load_config(p)
    assert cfg.deck_strict_types == ["dragon", "balloon"]


def test_defaults_when_absent(tmp_path):
    import json
    data = json.loads(EXAMPLE.read_text())
    for key in ("deck_strict_types", "deploy_jitter_px", "mirror_strategies",
                "tap_delay_jitter_pct", "another_device_wait_s", "connection_lost_point",
                "zoom_out_enabled", "zoom_out_pinches", "zoom_out_settle_s"):
        data.pop(key, None)
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    cfg = load_config(p)
    assert cfg.deploy_jitter_px == 38 and cfg.mirror_strategies is True
    # default zoom ada di kode (bukan hanya di config.example.json):
    assert cfg.zoom_out_enabled is True
    assert cfg.zoom_out_pinches == 3
    assert cfg.zoom_out_settle_s == 0.8


def test_example_config_zoom_defaults():
    cfg = load_config(EXAMPLE)
    assert cfg.zoom_out_enabled is True
    assert cfg.zoom_out_pinches == 3
    assert cfg.zoom_out_settle_s == 0.8


def test_invalid_zoom_fields_rejected(tmp_path):
    base = json.loads(EXAMPLE.read_text())
    for key, bad in (("zoom_out_pinches", 11), ("zoom_out_settle_s", -1)):
        data = json.loads(json.dumps(base))
        data[key] = bad
        p = tmp_path / "c.json"
        p.write_text(json.dumps(data))
        with pytest.raises(ConfigError, match=key):
            load_config(p)


def test_invalid_reliability_fields_rejected(tmp_path):
    import json
    from coclab.config import ConfigError
    import pytest
    base = json.loads(EXAMPLE.read_text())
    for key, bad in (("deploy_jitter_px", -1), ("tap_delay_jitter_pct", 95),
                     ("deck_strict_types", "dragon"), ("another_device_wait_s", 0)):
        data = json.loads(json.dumps(base))
        data[key] = bad
        p = tmp_path / "c.json"
        p.write_text(json.dumps(data))
        with pytest.raises(ConfigError):
            load_config(p)
