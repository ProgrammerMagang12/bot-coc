from pathlib import Path

from coclab.config import load_config
from coclab.loop import run
from coclab.vision import Match
from fakes import full_script, make_deps

EXAMPLE = Path(__file__).parent.parent / "config.example.json"


def test_happy_path_single_cycle_observe():
    states = []
    deps, adb = make_deps(full_script(), states)
    summary = run(load_config(EXAMPLE), mode="observe", cycles=1, deps=deps)
    assert summary.ok and summary.cycles_done == 1
    assert states[0] == "CONNECT" and "ATTACK" in states and states[-1] == "DONE"


def test_loot_low_clicks_next_and_retries_matchmaking():
    states = []
    script = full_script(**{"next.png": Match(True, 50, 50, 0.95)})
    deps, adb = make_deps(script, states)
    # per ronde: gold read1,read2 lalu elixir read1,read2
    loots = iter([100, 100, 50, 50, 999999, 999999, 999999, 999999])
    deps.ocr_digits = lambda img, engine=None: next(loots)
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok and states.count("MATCHMAKING") == 2


def test_elixir_threshold_enforced():
    states = []
    script = full_script(**{"next.png": Match(True, 50, 50, 0.95)})
    deps, adb = make_deps(script, states)
    # gold tinggi, elixir rendah → tetap loot_low
    loots = iter([999999, 999999, 10, 10, 999999, 999999, 999999, 999999])
    deps.ocr_digits = lambda img, engine=None: next(loots)
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok and states.count("MATCHMAKING") == 2


def test_loot_double_read_mismatch_is_fail_safe():
    deps, _ = make_deps(full_script(), [])
    seq = iter([100, 200])
    deps.ocr_digits = lambda img, engine=None: next(seq)
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert not summary.ok and "OCR" in summary.reason.upper()


def test_ocr_none_stops_by_default():
    deps, _ = make_deps(full_script(), [])
    deps.ocr_digits = lambda img, engine=None: None
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert not summary.ok and "OCR" in summary.reason.upper()  # policy stop


def test_ocr_none_with_policy_attack_continues(tmp_path):
    import json

    from coclab.config import load_config as lc

    data = json.loads(EXAMPLE.read_text())
    data["on_ocr_fail"] = "attack"
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    deps, _ = make_deps(full_script(), [])
    deps.ocr_digits = lambda img, engine=None: None
    summary = run(lc(p), "observe", 1, deps=deps)
    assert summary.ok


def test_return_home_timeout_stops():
    script = full_script()
    del script["returnhome.png"]  # returnhome tidak pernah ketemu
    deps, _ = make_deps(script, [])
    t = [-10]
    deps.monotonic = lambda: t.__setitem__(0, t[0] + 10) or t[0]  # +10s tiap panggilan
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert not summary.ok and "timeout" in summary.reason.lower()


def test_run_reports_clean_failure_when_wm_size_fails():
    from coclab.adb import AdbError

    deps, _ = make_deps(full_script(), [])

    def boom(_device):
        raise AdbError("adb command failed (rc=1): wm size")

    deps.adb.wm_size = boom
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert not summary.ok and "wm size" in summary.reason


def test_run_reports_clean_failure_when_template_missing():
    deps, _ = make_deps(full_script(), [])

    def boom(_img, _tpl, _threshold):
        raise ValueError("cannot read image: assets\\attack.png")

    deps.find_template = boom
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert not summary.ok and "attack.png" in summary.reason


def test_observe_mode_never_taps_end_to_end():
    from coclab.actions import Actions

    deps, adb = make_deps(full_script(), [])
    deps.actions_factory = lambda a, d, m, s: Actions(a, d, m, s)
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok and adb.taps == []


def test_matchmaking_clicks_attack2_confirm():
    states = []
    deps, adb = make_deps(full_script(), states)
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok
    assert (600, 700) in adb.taps  # tombol "Attack!" di layar army


def test_return_home_skips_missing_event_template():
    script = full_script(**{"returnhome.png": Match(False, 0, 0, 0.1)})
    calls = {"n": 0}

    def find_template(img, tpl, threshold):
        name = Path(tpl).name
        if name == "returnhome_event.png":
            raise ValueError("cannot read image: assets\\returnhome_event.png")
        if name == "returnhome.png":
            calls["n"] += 1
            if calls["n"] >= 2:
                return Match(True, 800, 700, 0.95)
        return script.get(name, Match(False, 0, 0, 0.0))

    deps, adb = make_deps(script, [])
    deps.find_template = find_template
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok


def test_live_attack_taps_card_first_legacy():
    from coclab.actions import Actions

    deps, adb = make_deps(full_script(), [])
    deps.actions_factory = lambda a, d, m, s: Actions(a, d, m, s)
    deps.load_strategies = lambda path: []
    cfg = load_config(EXAMPLE)
    summary = run(cfg, "live", 1, deps=deps)
    assert summary.ok
    card = (int(0.091 * 1600), int(0.933 * 900))
    drop = (int(0.35 * 1600), int(0.72 * 900))
    assert adb.swipes == []
    assert card in adb.taps and adb.taps.index(card) < adb.taps.index(drop)


def test_multi_drop_attack_taps_cards_then_points():
    from coclab.actions import Actions
    from coclab.strategy import Strategy

    states = []
    deps, adb = make_deps(full_script(), states)
    deps.actions_factory = lambda a, d, m, s: Actions(a, d, m, s)
    deps.load_strategies = lambda path: [
        Strategy(
            name="Test-A",
            dragon_drops=[[0.30, 0.60], [0.32, 0.62]],
            balloon_drops=[[0.34, 0.64]],
            wall_wrecker_drop=[0.36, 0.66],
        )
    ]
    cfg = load_config(EXAMPLE)
    summary = run(cfg, "live", 1, deps=deps)
    assert summary.ok
    assert adb.swipes == []
    assert adb.taps == [
        (1, 1),
        (1, 1),
        (600, 700),  # attack, find_match, attack2
        (int(0.091 * 1600), int(0.933 * 900)),  # kartu dragon
        (int(0.30 * 1600), int(0.60 * 900)),
        (int(0.32 * 1600), int(0.62 * 900)),
        (int(0.166 * 1600), int(0.933 * 900)),  # kartu balloon
        (int(0.34 * 1600), int(0.64 * 900)),
        (int(0.325 * 1600), int(0.933 * 900)),  # kartu wrecker
        (int(0.36 * 1600), int(0.66 * 900)),
        (int(0.065 * 1600), int(0.75 * 900)),  # end battle
        (int(0.614 * 1600), int(0.648 * 900)),  # confirm
        (int(0.497 * 1600), int(0.849 * 900)),  # return home
    ]


def test_wall_upgrade_wired_when_enabled(monkeypatch, tmp_path):
    import json

    from coclab import loop as loop_mod

    data = json.loads(EXAMPLE.read_text())
    data["wall_upgrade"]["enabled"] = True
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))

    calls = {"n": 0}

    def fake_wall(cfg, **kwargs):
        calls["n"] += 1
        return type("R", (), {"status": "skipped", "reason": "test"})()

    monkeypatch.setattr(loop_mod.wallupgrade, "run_wall_upgrade", fake_wall)
    deps, _ = make_deps(full_script(), [])
    summary = run(load_config(p), "observe", 1, deps=deps)
    assert summary.ok and calls["n"] == 1


def test_wall_upgrade_not_called_when_disabled(monkeypatch):
    from coclab import loop as loop_mod

    calls = {"n": 0}

    def fake_wall(cfg, **kwargs):
        calls["n"] += 1
        return type("R", (), {"status": "skipped", "reason": "test"})()

    monkeypatch.setattr(loop_mod.wallupgrade, "run_wall_upgrade", fake_wall)
    deps, _ = make_deps(full_script(), [])
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok and calls["n"] == 0
