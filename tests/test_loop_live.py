# tests/test_loop_live.py — aksi nyata (live) memakai Actions asli di atas fake adb
from pathlib import Path

from coclab.actions import Actions
from coclab.config import load_config
from coclab.loop import run
from fakes import full_script, make_deps

EXAMPLE = Path(__file__).parent.parent / "config.example.json"


def test_live_attack_sequence_coordinates():
    states = []
    deps, adb = make_deps(full_script(), states)
    deps.actions_factory = lambda a, d, m, s: Actions(a, d, m, s)  # gerbang nyata
    summary = run(load_config(EXAMPLE), "live", 1, deps=deps)
    assert summary.ok
    expected = [
        (int(0.35 * 1600), int(0.72 * 900)),
        (int(0.065 * 1600), int(0.75 * 900)),
        (int(0.614 * 1600), int(0.648 * 900)),
        (int(0.497 * 1600), int(0.849 * 900)),
    ]
    assert adb.taps[-4:] == expected  # drop point, end battle, confirm, return home
