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
    deps.read_loot = lambda img: next(loots)
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok and states.count("MATCHMAKING") == 2


def test_elixir_threshold_enforced():
    states = []
    script = full_script(**{"next.png": Match(True, 50, 50, 0.95)})
    deps, adb = make_deps(script, states)
    # gold tinggi, elixir rendah → tetap loot_low
    loots = iter([999999, 999999, 10, 10, 999999, 999999, 999999, 999999])
    deps.read_loot = lambda img: next(loots)
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok and states.count("MATCHMAKING") == 2


def test_loot_retry_after_bad_read():
    states = []
    deps, adb = make_deps(full_script(), states)
    # gold: mismatch (100 vs 200 → None) lalu retry 999999,999999; elixir 999999,999999
    loots = iter([100, 200, 999999, 999999, 999999, 999999])
    deps.read_loot = lambda img: next(loots)
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
    # dua read utk gold semuanya None → skip base; ronde 2 normal → attack
    loots = iter([None, None, 999999, 999999, 999999, 999999])
    deps.read_loot = lambda img: next(loots)
    summary = run(lc(p), "observe", 1, deps=deps)
    assert summary.ok and states.count("MATCHMAKING") == 2


def test_loot_recovers_on_second_capture():
    states = []
    deps, adb = make_deps(full_script(), states)
    # capture pertama tak terbaca (dua varian None), capture kedua bersih
    loots = iter([None, None, 999999, 999999, 999999, 999999])
    deps.read_loot = lambda img: next(loots)
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
    deps.read_loot = lambda img: next(seq)
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
    deps.read_loot = lambda img: None
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
    deps.read_loot = lambda img: None
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
    speed = (int(0.959 * 1600), int(0.572 * 900))
    assert body[38:40] == [speed, speed]  # ketuk speed 2x (x1 -> x4)
    # results screen langsung terlihat → battle dianggap selesai lebih awal:
    # End Battle/Confirm tidak ditap, langsung Return Home
    assert body[40] == (int(0.497 * 1600), int(0.849 * 900))
    assert len(body) == 41


def test_min_dark_enforced(tmp_path):
    import json

    data = json.loads(EXAMPLE.read_text())
    data["min_dark"] = 5000
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    states = []
    script = full_script(**{"next.png": Match(True, 50, 50, 0.95)})
    deps, adb = make_deps(script, states)
    # ronde 1: dark 4000 < 5000 → low; ronde 2: semua tinggi → attack
    loots = iter(
        [
            999999, 999999, 999999, 999999, 4000, 4000,
            999999, 999999, 999999, 999999, 6000, 6000,
        ]
    )
    deps.read_loot = lambda img: next(loots)
    summary = run(load_config(p), "observe", 1, deps=deps)
    assert summary.ok and states.count("MATCHMAKING") == 2


def test_stop_flag_ends_cycle():
    states = []
    deps, adb = make_deps(full_script(), states)
    deps.should_stop = lambda: True
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert not summary.ok and "stopped" in summary.reason.lower()
    assert adb.taps == []


def test_battle_wait_normal_end_when_results_appear_late():
    from coclab.strategy import Strategy

    states = []
    script = full_script()
    script["returnhome.png"] = Match(False, 0, 0, 0.1)
    deps, adb = make_deps(script, states)
    deps.load_strategies = lambda path: [
        Strategy(
            name="L",
            dragon_drops=[[0.50, 0.50]],
            balloon_drops=[[0.51, 0.51]],
            wall_wrecker_drop=None,
        )
    ]
    end_battle = (int(0.065 * 1600), int(0.75 * 900))
    orig = deps.find_template

    def find_template(img, tpl, threshold):
        if Path(tpl).name == "returnhome.png" and end_battle in adb.taps:
            return Match(True, 700, 700, 0.95)
        return orig(img, tpl, threshold)

    deps.find_template = find_template
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok
    assert end_battle in adb.taps
    assert (int(0.614 * 1600), int(0.648 * 900)) in adb.taps
    # hero skills ditap pada 7 delay (5..60 s) → 2 titik x 7
    assert adb.taps.count((int(0.404 * 1600), int(0.76 * 900))) == 7
    assert adb.taps.count((int(0.445 * 1600), int(0.76 * 900))) == 7


def test_disconnect_popup_taps_reload():
    from coclab.loop import _Session

    states = []
    deps, adb = make_deps(full_script(), states)
    deps.ocr_boxes = lambda img: [("Anyone there?", 575, 187), ("RELOAD GAME", 280, 407)]
    session = _Session(load_config(EXAMPLE), "observe", deps)
    session.device = "127.0.0.1:5555"
    session.actions = deps.actions_factory(deps.adb, session.device, "observe", (1600, 900))
    assert session._handle_disconnected(None) is True
    assert (280, 407) in adb.taps

def test_no_disconnect_returns_false():
    from coclab.loop import _Session

    states = []
    deps, adb = make_deps(full_script(), states)
    deps.ocr_boxes = lambda img: [("Available Loot:", 100, 100)]
    session = _Session(load_config(EXAMPLE), "observe", deps)
    session.device = "127.0.0.1:5555"
    session.actions = deps.actions_factory(deps.adb, session.device, "observe", (1600, 900))
    assert session._handle_disconnected(None) is False
    assert adb.taps == []


def test_find_attack_retries_until_button_appears():
    states = []
    script = full_script()
    script["attack.png"] = Match(False, 0, 0, 0.1)
    deps, adb = make_deps(script, states)
    adb.shell_fn = (
        lambda cmd: "com.supercell.clashofclans" if "ps" in cmd else "ok"
    )  # CoC dianggap jalan → murni tes retry
    calls = {"n": 0}
    orig = deps.find_template

    def find_template(img, tpl, threshold):
        if Path(tpl).name == "attack.png":
            calls["n"] += 1
            if calls["n"] >= 4:
                return Match(True, 700, 750, 0.95)
        return orig(img, tpl, threshold)

    deps.find_template = find_template
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok  # bot waiting + retry, tidak langsung menyerah


def test_find_attack_launches_coc_when_closed():
    states = []
    script = full_script()
    script["attack.png"] = Match(False, 0, 0, 0.1)
    deps, adb = make_deps(script, states)

    def shell_fn(cmd):
        if "ps -A" in cmd:
            return ""
        if "resolve-activity" in cmd:
            return "priority=0 x\ncom.supercell.clashofclans/com.supercell.titan.GameApp"
        if "am start" in cmd:
            return "Starting: Intent { cmp=com.supercell.clashofclans/com.supercell.titan.GameApp }"
        return "ok"

    adb.shell_fn = shell_fn
    orig = deps.find_template

    def launched():
        return any("am start" in c for c in adb.shells)

    def find_template(img, tpl, threshold):
        name = Path(tpl).name
        if name == "attack.png" and launched():
            return Match(True, 700, 750, 0.95)
        if name == "returnhome.png" and not launched():
            return Match(False, 0, 0, 0.1)  # sebelum launch: jangan sweep dulu
        return orig(img, tpl, threshold)

    deps.find_template = find_template
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok
    assert any("am start" in c for c in adb.shells)


def test_de_full_stops_and_closes_coc(tmp_path):
    import json

    data = json.loads(EXAMPLE.read_text())
    data["de_full_value"] = 100000
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    states = []
    deps, adb = make_deps(full_script(), states)
    deps.read_de = lambda img: 171828
    summary = run(load_config(p), "observe", 1, deps=deps)
    assert summary.ok and "DE" in summary.reason
    assert adb.shells and "force-stop" in adb.shells[0]
    assert adb.taps == []  # berhenti sebelum menyerang


def test_army_empty_stops_attack():
    states = []
    deps, adb = make_deps(full_script(), states)
    deps.read_badge = lambda img: 1
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok and "pasukan" in summary.reason
    end_battle = (int(0.065 * 1600), int(0.75 * 900))
    assert end_battle in adb.taps  # langsung end battle, tidak deploy


def test_collect_points_tapped_at_home(tmp_path):
    import json

    data = json.loads(EXAMPLE.read_text())
    data["collect_points"] = [[0.2, 0.5], [0.3, 0.5]]
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    states = []
    deps, adb = make_deps(full_script(), states)
    summary = run(load_config(p), "observe", 1, deps=deps)
    assert summary.ok
    p1 = (int(0.2 * 1600), int(0.5 * 900))
    p2 = (int(0.3 * 1600), int(0.5 * 900))
    # ditap sekali saat mulai (sebelum Click Attack) + sekali setelah balik home
    assert adb.taps.count(p1) == 2 and adb.taps.count(p2) == 2
    assert adb.taps.index(p1) < adb.taps.index((1, 1))  # collect sebelum serang


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


def test_claim_event_reward_taps_continue_template():
    from coclab.loop import _Session

    states = []
    script = full_script()
    del script["attack.png"]  # home tidak pernah ketemu di test ini
    script["continue.png"] = Match(True, 815, 812, 0.95)
    deps, adb = make_deps(script, states)
    session = _Session(load_config(EXAMPLE), "observe", deps)
    session.device = "127.0.0.1:5555"
    session.actions = deps.actions_factory(deps.adb, session.device, "observe", (1600, 900))
    result = session._claim_event_reward(Match(True, 798, 770, 0.97))
    assert not result.ok
    assert (798, 770) in adb.taps
    assert adb.taps.count((800, 450)) == 4
    assert (815, 812) in adb.taps  # Continue via template match


def test_tap_until_home_taps_popup_points():
    from coclab.loop import _Session

    states = []
    script = full_script()
    del script["attack.png"]  # tidak pernah home di test ini
    del script["returnhome.png"]
    deps, adb = make_deps(script, states)
    session = _Session(load_config(EXAMPLE), "observe", deps)
    session.device = "127.0.0.1:5555"
    session.actions = deps.actions_factory(deps.adb, session.device, "observe", (1600, 900))
    result = session._tap_until_home(max_rounds=2)
    assert result is False
    okay = (int(0.495 * 1600), int(0.82 * 900))
    not_now = (int(0.38 * 1600), int(0.68 * 900))
    assert okay in adb.taps  # tombol Okay Star Bonus
    assert not_now in adb.taps  # tombol Not Now Notifications


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
