# tests/test_loop_live.py — aksi nyata (live) memakai Actions asli di atas fake adb
from pathlib import Path

from coclab.actions import Actions
from coclab.config import load_config
from coclab.loop import run
from fakes import full_script, make_deps

EXAMPLE = Path(__file__).parent.parent / "config.example.json"


def test_live_attack_taps_card_then_drop_then_end_confirm_home():
    deps, adb = make_deps(full_script(), [])
    deps.actions_factory = lambda a, d, m, s: Actions(a, d, m, s)
    cfg = load_config(EXAMPLE)
    summary = run(cfg, "live", 1, deps=deps)
    assert summary.ok
    card = (int(0.091 * 1600), int(0.933 * 900))
    drop = (int(0.35 * 1600), int(0.72 * 900))
    assert adb.swipes == []
    assert card in adb.taps and adb.taps.index(card) < adb.taps.index(drop)
    expected_tail = [
        (int(0.065 * 1600), int(0.75 * 900)),  # end battle
        (int(0.614 * 1600), int(0.648 * 900)),  # confirm
        (int(0.497 * 1600), int(0.849 * 900)),  # return home
    ]
    assert adb.taps[-3:] == expected_tail
