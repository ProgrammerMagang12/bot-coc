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
