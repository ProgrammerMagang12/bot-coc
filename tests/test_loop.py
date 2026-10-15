from pathlib import Path

from coclab.config import load_config
from coclab.loop import run
from fakes import full_script, make_deps

EXAMPLE = Path(__file__).parent.parent / "config.example.json"


def test_happy_path_single_cycle_observe():
    states = []
    deps, adb = make_deps(full_script(), states)
    summary = run(load_config(EXAMPLE), mode="observe", cycles=1, deps=deps)
    assert summary.ok and summary.cycles_done == 1
    assert states[0] == "CONNECT" and "ATTACK" in states and states[-1] == "DONE"
