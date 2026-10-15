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


def test_loot_retry_after_bad_read():
    states = []
    deps, adb = make_deps(full_script(), states)
    # gold: mismatch (100 vs 200 → None) lalu retry 999999,999999; elixir 999999,999999
    loots = iter([100, 200, 999999, 999999, 999999, 999999])
    deps.ocr_digits = lambda img, engine=None: next(loots)
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok


def test_ocr_fail_policy_next_skips_base(tmp_path):
    import json

    from coclab.config import load_config as lc

    data = json.loads(EXAMPLE.read_text())
    data["on_ocr_fail"] = "next"
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))

    states = []
    script = full_script(**{"next.png": Match(True, 50, 50, 0.95)})
    deps, adb = make_deps(script, states)
    # dua capture utk gold semuanya None → skip base; ronde 2 normal → attack
    loots = iter([None, None, None, None, 999999, 999999, 999999, 999999])
    deps.ocr_digits = lambda img, engine=None: next(loots)
    summary = run(lc(p), "observe", 1, deps=deps)
    assert summary.ok and states.count("MATCHMAKING") == 2


def test_loot_recovers_on_second_capture():
    states = []
    deps, adb = make_deps(full_script(), states)
    # capture pertama tak terbaca (dua varian None), capture kedua bersih
    loots = iter([None, None, 999999, 999999, 999999, 999999])
    deps.ocr_digits = lambda img, engine=None: next(loots)
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok


def test_loot_double_read_mismatch_is_fail_safe(tmp_path):
    import json

    from coclab.config import load_config as lc

    data = json.loads(EXAMPLE.read_text())
    data["on_ocr_fail"] = "stop"
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    deps, _ = make_deps(full_script(), [])
    seq = iter([100, 200, 100, 200])  # dua percobaan pun mismatch
    deps.ocr_digits = lambda img, engine=None: next(seq)
    summary = run(lc(p), "observe", 1, deps=deps)
    assert not summary.ok and "OCR" in summary.reason.upper()


def test_ocr_none_with_policy_stop_fails(tmp_path):
    import json

    from coclab.config import load_config as lc

    data = json.loads(EXAMPLE.read_text())
    data["on_ocr_fail"] = "stop"
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    deps, _ = make_deps(full_script(), [])
    deps.ocr_digits = lambda img, engine=None: None
    summary = run(lc(p), "observe", 1, deps=deps)
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
    assert adb.taps[:3] == [(1, 1), (1, 1), (600, 700)]
    body = adb.taps[3:]
    # wrecker dulu (urutan CROWZ), lalu dragon, balloon, extra troop (amount dari army)
    assert body[0] == (int(0.325 * 1600), int(0.933 * 900))
    assert body[1] == (int(0.36 * 1600), int(0.66 * 900))
    assert body[2] == (int(0.091 * 1600), int(0.933 * 900))
    dragon = body[3:16]  # army dragon_drops=13 → siklus 2 titik
    assert len(dragon) == 13
    assert dragon[0] == (int(0.30 * 1600), int(0.60 * 900))
    assert dragon[1] == (int(0.32 * 1600), int(0.62 * 900))
    assert body[16] == (int(0.166 * 1600), int(0.933 * 900))
    assert body[17:35] == [(int(0.34 * 1600), int(0.64 * 900))] * 18
    assert body[35] == (int(0.24 * 1600), int(0.933 * 900))
    assert body[36:38] == [
        (int(0.30 * 1600), int(0.60 * 900)),
        (int(0.32 * 1600), int(0.62 * 900)),
    ]
    assert body[38:] == [
        (int(0.065 * 1600), int(0.75 * 900)),
        (int(0.614 * 1600), int(0.648 * 900)),
        (int(0.497 * 1600), int(0.849 * 900)),
    ]


def test_army_counts_cycle_strategy_points(tmp_path):
    import json

    from coclab.strategy import Strategy

    data = json.loads(EXAMPLE.read_text())
    data["army"] = {"dragon_drops": 5, "balloon_drops": 1, "wall_wrecker_drop": 1}
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    states = []
    deps, adb = make_deps(full_script(), states)
    deps.load_strategies = lambda path: [
        Strategy(
            name="T",
            dragon_drops=[[0.10, 0.10], [0.20, 0.20]],
            balloon_drops=[[0.30, 0.30]],
            wall_wrecker_drop=None,
        )
    ]
    summary = run(load_config(p), "observe", 1, deps=deps)
    assert summary.ok
    cycle = [(int(0.10 * 1600), int(0.10 * 900)), (int(0.20 * 1600), int(0.20 * 900))]
    assert [t for t in adb.taps if t in cycle] == [
        cycle[0],
        cycle[1],
        cycle[0],
        cycle[1],
        cycle[0],
    ]


def test_heroes_deployed_at_scenario_positions():
    from coclab.strategy import Strategy

    states = []
    deps, adb = make_deps(full_script(), states)
    deps.load_strategies = lambda path: [
        Strategy(
            name="H",
            dragon_drops=[[0.50, 0.50]],
            balloon_drops=[[0.51, 0.51]],
            wall_wrecker_drop=None,
            hero_positions=[[0.30, 0.40], [0.70, 0.60]],
        )
    ]
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok
    hero1_card = (int(0.424 * 1600), int(0.91 * 900))
    hero2_card = (int(0.502 * 1600), int(0.91 * 900))
    pos1 = (int(0.30 * 1600), int(0.40 * 900))
    pos2 = (int(0.70 * 1600), int(0.60 * 900))
    assert adb.taps.index(hero1_card) < adb.taps.index(pos1)
    assert adb.taps.index(pos1) < adb.taps.index(hero2_card)
    assert adb.taps.index(hero2_card) < adb.taps.index(pos2)


def test_spells_cast_at_scenario_positions():
    from coclab.strategy import Strategy

    states = []
    deps, adb = make_deps(full_script(), states)
    deps.load_strategies = lambda path: [
        Strategy(
            name="S",
            dragon_drops=[[0.50, 0.50]],
            balloon_drops=[[0.51, 0.51]],
            wall_wrecker_drop=None,
            rage_spell_positions=[[0.40, 0.40], [0.45, 0.45]],
            freeze_spell_positions=[[0.60, 0.60]],
        )
    ]
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok
    rage_card = (int(0.58 * 1600), int(0.933 * 900))
    freeze_card = (int(0.658 * 1600), int(0.933 * 900))
    rage_a = (int(0.40 * 1600), int(0.40 * 900))
    rage_b = (int(0.45 * 1600), int(0.45 * 900))
    freeze_pt = (int(0.60 * 1600), int(0.60 * 900))
    assert rage_card in adb.taps and freeze_card in adb.taps
    assert adb.taps.count(rage_a) == 2 and adb.taps.count(rage_b) == 2
    assert adb.taps.count(freeze_pt) == 3
    assert adb.taps.index(rage_card) < adb.taps.index(rage_a)
    assert adb.taps.index(freeze_card) < adb.taps.index(freeze_pt)
    assert adb.taps.index(rage_a) < adb.taps.index(freeze_card)


def test_return_home_event_claim_flow():
    from coclab.strategy import Strategy

    states = []
    script = full_script()
    del script["returnhome.png"]
    script["claim_reward.png"] = Match(True, 798, 770, 0.97)
    deps, adb = make_deps(script, states)
    deps.load_strategies = lambda path: [
        Strategy(
            name="E",
            dragon_drops=[[0.20, 0.20]],
            balloon_drops=[[0.21, 0.21]],
            wall_wrecker_drop=None,
        )
    ]
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok
    assert (798, 770) in adb.taps  # tap Claim Reward di posisi hasil template match
    assert adb.taps.count((800, 450)) == 4  # buka chest: 4x tap layar
    cont = (int(0.49 * 1600), int(0.78 * 900))
    assert cont in adb.taps  # tap Continue sampai home


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
