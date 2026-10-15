import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))

import import_crowz_strategies as ics  # noqa: E402

from coclab.strategy import load_strategies  # noqa: E402


def _crowz_data(name="Scenario X"):
    return {
        "Strategies": [
            {
                "Name": name,
                "DragonDrops": [[0.1, 0.2], [0.3, 0.4]],
                "BalloonDrops": [[0.5, 0.6]],
                "WallWreckerDrop": [0.2, 0.3],
                "HeroPositions": [[0.11, 0.22]],
                "RageSpellPositions": [[0.7, 0.8]],
                "FreezeSpellPositions": [[0.9, 0.1]],
            }
        ]
    }


def test_convert_crowz_pascal_case_to_our_schema(tmp_path):
    src = tmp_path / "crowz.json"
    src.write_text(json.dumps(_crowz_data()))
    out = tmp_path / "ours.json"
    written = ics.convert(src, out)
    assert written == 1
    s = load_strategies(out)[0]
    assert s.name == "Scenario X"
    assert s.dragon_drops == [[0.1, 0.2], [0.3, 0.4]]
    assert s.balloon_drops == [[0.5, 0.6]]
    assert s.wall_wrecker_drop == [0.2, 0.3]
    assert s.hero_positions == [[0.11, 0.22]]
    assert s.rage_spell_positions == [[0.7, 0.8]]
    assert s.freeze_spell_positions == [[0.9, 0.1]]


def test_convert_overwrites_without_append_and_appends_with_it(tmp_path):
    src = tmp_path / "crowz.json"
    src.write_text(json.dumps(_crowz_data("S1")))
    out = tmp_path / "ours.json"
    ics.convert(src, out)
    ics.convert(src, out, append=True)
    assert [s.name for s in load_strategies(out)] == ["S1", "S1"]
    ics.convert(src, out)  # overwrite
    assert len(load_strategies(out)) == 1
