from pathlib import Path

import numpy as np

from coclab.digits import read_loot_number
from coclab.vision import load_image

FIXTURES = Path(__file__).parent / "fixtures"


def test_read_loot_fixtures_exact():
    assert read_loot_number(load_image(FIXTURES / "gold_016.png")) == 1839970
    assert read_loot_number(load_image(FIXTURES / "gold_005.png")) == 2194867
    assert read_loot_number(load_image(FIXTURES / "gold_027.png")) == 2019901
    assert read_loot_number(load_image(FIXTURES / "elix_022.png")) == 491889


def test_read_loot_blank_returns_none():
    assert read_loot_number(np.zeros((40, 200, 3), np.uint8)) is None
