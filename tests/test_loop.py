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
    # Template tak terbaca kini = "tidak ketemu" (graceful); alur harus berakhir
    # dengan timeout bersih, bukan crash atau loop tak berujung.
    t = [-10]
    deps.monotonic = lambda: t.__setitem__(0, t[0] + 10) or t[0]  # +10s tiap panggilan
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert not summary.ok and "timeout" in summary.reason.lower()


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


def test_multi_drop_attack_taps_cards_then_points(tmp_path):
    import json

    from coclab.actions import Actions
    from coclab.strategy import Strategy

    data = json.loads(EXAMPLE.read_text())
    data["deploy_jitter_px"] = 0  # urutan/titik persis; jitter diuji terpisah
    data["mirror_strategies"] = False
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))

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
    cfg = load_config(p)
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
    assert session._handle_popups(None) is True
    assert (280, 407) in adb.taps

def test_no_disconnect_returns_false():
    from coclab.loop import _Session

    states = []
    deps, adb = make_deps(full_script(), states)
    deps.ocr_boxes = lambda img: [("Available Loot:", 100, 100)]
    session = _Session(load_config(EXAMPLE), "observe", deps)
    session.device = "127.0.0.1:5555"
    session.actions = deps.actions_factory(deps.adb, session.device, "observe", (1600, 900))
    assert session._handle_popups(None) is False
    assert adb.taps == []


def test_another_device_waits_during_battle_without_tap():
    """Popup muncul SAAT battle-wait (setelah STATE ATTACK) → tidak tap, tunggu, lanjut."""
    from coclab.vision import Match
    script = full_script()
    seen = {"n": 0}
    states = []
    deps, adb = make_deps(script, states)
    base_ft = deps.find_template

    def ft(img, tpl, threshold):
        from pathlib import Path
        if Path(tpl).name == "Another_device.png":
            if "ATTACK" in states:          # hanya muncul saat battle-wait
                seen["n"] += 1
                return Match(seen["n"] <= 2, 500, 400, 0.99)
            return Match(False, 0, 0, 0.0)
        return base_ft(img, tpl, threshold)

    deps.find_template = ft
    sleeps = []
    base_sleep = deps.sleep
    deps.sleep = lambda s: sleeps.append(s) or base_sleep(s)
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok and seen["n"] >= 3
    assert not any(abs(tx - 500) <= 3 and abs(ty - 400) <= 3 for tx, ty in adb.taps)
    assert sleeps.count(1.0) >= 2  # menunggu dalam potongan 1 detik


def test_another_device_stop_is_responsive():
    from coclab.vision import Match
    deps, adb = make_deps(full_script(), [])
    base_ft = deps.find_template
    state = {"stops": 0}

    def ft(img, tpl, threshold):
        from pathlib import Path
        if Path(tpl).name == "Another_device.png":
            return Match(True, 500, 400, 0.99)
        return base_ft(img, tpl, threshold)

    deps.find_template = ft
    deps.should_stop = lambda: state.__setitem__("stops", state["stops"] + 1) or state["stops"] > 2
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert not summary.ok and "stopped" in summary.reason.lower()


def test_client_error_restarts_coc():
    from coclab.vision import Match
    script = full_script(**{"Client_error!.png": Match(True, 500, 400, 0.99)})
    seen = {"n": 0}
    deps, adb = make_deps(script, [])
    base_ft = deps.find_template

    def ft(img, tpl, threshold):
        from pathlib import Path
        if Path(tpl).name == "Client_error!.png":
            seen["n"] += 1
            return Match(seen["n"] <= 1, 500, 400, 0.99)
        return base_ft(img, tpl, threshold)

    deps.find_template = ft
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok
    assert any("am start" in c for c in adb.shells)


def test_connection_lost_taps_reconnect_point(tmp_path):
    import json
    data = json.loads(EXAMPLE.read_text())
    data["connection_lost_point"] = [0.5, 0.55]
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    from coclab.vision import Match
    script = full_script(**{"Connection_lost.png": Match(True, 500, 400, 0.99)})
    seen = {"n": 0}
    deps, adb = make_deps(script, [])
    base_ft = deps.find_template

    def ft(img, tpl, threshold):
        from pathlib import Path
        if Path(tpl).name == "Connection_lost.png":
            seen["n"] += 1
            return Match(seen["n"] <= 1, 500, 400, 0.99)
        return base_ft(img, tpl, threshold)

    deps.find_template = ft
    summary = run(load_config(p), "observe", 1, deps=deps)
    assert summary.ok and (800, 495) in adb.taps


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
            # CoC "hidup" setelah am start dijalankan
            return (
                "com.supercell.clashofclans"
                if any("am start" in c for c in adb.shells)
                else ""
            )
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
    # Zoom-out (default on) menulis skrip pinch sebelum force-stop di jalur ini;
    # dimatikan agar pin lama "shell pertama = force-stop" tetap utuh (fokus DE).
    data["zoom_out_enabled"] = False
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    states = []
    deps, adb = make_deps(full_script(), states)
    deps.read_de = lambda img: 171828
    summary = run(load_config(p), "observe", 1, deps=deps)
    assert summary.ok and "DE" in summary.reason
    assert adb.shells and "force-stop" in adb.shells[0]
    assert adb.taps == []  # berhenti sebelum menyerang


def test_army_mismatch_stops_when_no_train_points():
    states = []
    deps, adb = make_deps(full_script(), states)
    deps.read_badge = lambda img: 1
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok and "pasukan" in summary.reason
    end_battle = (int(0.065 * 1600), int(0.75 * 900))
    assert end_battle in adb.taps  # langsung end battle, tidak deploy


def test_army_type_mismatch_detected():
    states = []
    script = full_script()
    script["dragon_card.png"] = Match(False, 0, 0, 0.4)  # kompi manual tanpa dragon
    deps, adb = make_deps(script, states)
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok and "pasukan" in summary.reason
    end_battle = (int(0.065 * 1600), int(0.75 * 900))
    assert end_battle in adb.taps  # end battle, tidak deploy


def test_build_army_clear_build_verify(tmp_path):
    import json

    data = json.loads(EXAMPLE.read_text())
    data["army"] = {
        "dragon_drops": 2,
        "balloon_drops": 1,
        "wall_wrecker_drop": 1,
    }
    data["train_ui"] = {
        "army_button": [0.05, 0.70],
        "clear_troops": [0.90, 0.20],
        "clear_okay": [0.60, 0.60],
        "grid": {"dragon_drops": [0.40, 0.60], "balloon_drops": [0.45, 0.60]},
        "close_button": [0.95, 0.05],
    }
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    states = []
    deps, adb = make_deps(full_script(), states)
    badges = iter([1, 2])  # pertama kurang (mismatch), setelah build pas
    deps.read_badge = lambda img: next(badges)
    summary = run(load_config(p), "observe", 1, deps=deps)
    assert summary.ok and summary.cycles_done == 1
    assert (int(0.05 * 1600), int(0.70 * 900)) in adb.taps  # buka panel
    assert (int(0.90 * 1600), int(0.20 * 900)) in adb.taps  # trash troops
    assert (int(0.60 * 1600), int(0.60 * 900)) in adb.taps  # Okay confirm
    assert adb.taps.count((int(0.40 * 1600), int(0.60 * 900))) == 2  # dragon x2
    assert adb.taps.count((int(0.45 * 1600), int(0.60 * 900))) == 1  # balloon x1
    assert (int(0.95 * 1600), int(0.05 * 900)) in adb.taps  # tutup


def test_coc_crash_mid_matchmaking_relaunches(tmp_path):
    states = []
    script = full_script()
    deps, adb = make_deps(script, states)
    calls = {"n": 0}

    def shell_fn(cmd):
        if "ps -A" in cmd:
            calls["n"] += 1
            return "" if calls["n"] == 1 else "com.supercell.clashofclans"
        return "ok"

    adb.shell_fn = shell_fn
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok and summary.cycles_done == 1
    assert any("am start" in c for c in adb.shells)  # CoC dibuka ulang


def test_build_army_recipe_mode_at_menu(tmp_path):
    import json

    data = json.loads(EXAMPLE.read_text())
    data["train_ui"] = {
        "army_button": [0.1125, 0.9478],
        "recipe_tab": [0.5, 0.1022],
        "recipe_use": [0.9338, 0.2589],
        "recipe_confirm": [0.6113, 0.6467],
        "close_button": [0.965, 0.0911],
    }
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    states = []
    deps, adb = make_deps(full_script(), states)
    summary = run(load_config(p), "observe", 1, deps=deps)
    assert summary.ok and summary.cycles_done == 1
    assert (int(0.1125 * 1600), int(0.9478 * 900)) in adb.taps  # Edit Army
    assert (int(0.5 * 1600), int(0.1022 * 900)) in adb.taps  # tab resep
    assert (int(0.9338 * 1600), int(0.2589 * 900)) in adb.taps  # Use
    assert (int(0.6113 * 1600), int(0.6467 * 900)) in adb.taps  # Okay konfirmasi
    assert (int(0.965 * 1600), int(0.0911 * 900)) in adb.taps  # tutup


def test_build_mode_clears_then_taps_grid(tmp_path):
    import json

    data = json.loads(EXAMPLE.read_text())
    data["train_mode"] = "build"
    data["army"] = {
        "dragon_drops": 2,
        "balloon_drops": 1,
        "rage_spell": 1,
        "freeze_spell": 1,
    }
    data["train_ui"] = {
        "army_button": [0.05, 0.70],
        "clear_troops": [0.90, 0.20],
        "clear_spells": [0.77, 0.48],
        "clear_okay": [0.60, 0.60],
        "spell_edit": [0.60, 0.59],
        "grid": {
            "dragon_drops": [0.40, 0.60],
            "balloon_drops": [0.45, 0.60],
            "rage_spell": [0.17, 0.68],
            "freeze_spell": [0.27, 0.68],
        },
        "close_button": [0.95, 0.05],
    }
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    states = []
    deps, adb = make_deps(full_script(), states)
    badges = iter([1, 2])  # gate pertama mismatch -> build; setelah build pas
    deps.read_badge = lambda img: next(badges)
    summary = run(load_config(p), "observe", 1, deps=deps)
    assert summary.ok and summary.cycles_done == 1
    # clear: troops + spells + Okay confirm
    assert (int(0.90 * 1600), int(0.20 * 900)) in adb.taps
    assert (int(0.77 * 1600), int(0.48 * 900)) in adb.taps
    assert adb.taps.count((int(0.60 * 1600), int(0.60 * 900))) >= 1
    # buka picker + bangun troops
    assert (int(0.5913 * 1600), int(0.3333 * 900)) in adb.taps
    assert adb.taps.count((int(0.40 * 1600), int(0.60 * 900))) == 2
    assert adb.taps.count((int(0.45 * 1600), int(0.60 * 900))) == 1
    # spell: buka daftar spell + rage/freeze
    assert (int(0.60 * 1600), int(0.59 * 900)) in adb.taps
    assert adb.taps.count((int(0.17 * 1600), int(0.68 * 900))) == 1
    assert adb.taps.count((int(0.27 * 1600), int(0.68 * 900))) == 1


def test_waits_for_menu_detects_template(tmp_path):
    from coclab.loop import _Session

    states = []
    deps, adb = make_deps(full_script(), states)
    session = _Session(load_config(EXAMPLE), "observe", deps)
    session.device = "127.0.0.1:5555"
    session.actions = deps.actions_factory(deps.adb, session.device, "observe", (1600, 900))
    assert session._waits_for_menu() is True

    script = full_script()
    script["find_match.png"] = Match(False, 0, 0, 0.1)
    deps2, _adb2 = make_deps(script, [])
    session2 = _Session(load_config(EXAMPLE), "observe", deps2)
    session2.device = "127.0.0.1:5555"
    session2.actions = deps2.actions_factory(deps2.adb, session2.device, "observe", (1600, 900))
    assert session2._waits_for_menu(tries=3) is False


def test_army_mismatch_trains_then_retries(tmp_path):
    import json

    data = json.loads(EXAMPLE.read_text())
    data["train_points"] = [[0.1, 0.1], [0.2, 0.2]]
    data["train_wait_s"] = 0
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    states = []
    deps, adb = make_deps(full_script(), states)
    badges = iter([1, 13])  # pertama mismatch; setelah dilatih siap
    deps.read_badge = lambda img: next(badges)
    summary = run(load_config(p), "observe", 1, deps=deps)
    assert summary.ok and summary.cycles_done == 1
    assert (int(0.1 * 1600), int(0.1 * 900)) in adb.taps  # klik latih
    assert (int(0.2 * 1600), int(0.2 * 900)) in adb.taps


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
    data["deploy_jitter_px"] = 0  # siklus titik persis; jitter diuji terpisah
    data["mirror_strategies"] = False
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


def test_heroes_deployed_at_scenario_positions(tmp_path):
    import json

    from coclab.strategy import Strategy

    data = json.loads(EXAMPLE.read_text())
    data["deploy_jitter_px"] = 0  # posisi hero persis; jitter diuji terpisah
    data["mirror_strategies"] = False
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))

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
    summary = run(load_config(p), "observe", 1, deps=deps)
    assert summary.ok
    hero1_card = (int(0.424 * 1600), int(0.91 * 900))
    hero2_card = (int(0.502 * 1600), int(0.91 * 900))
    pos1 = (int(0.30 * 1600), int(0.40 * 900))
    pos2 = (int(0.70 * 1600), int(0.60 * 900))
    assert adb.taps.index(hero1_card) < adb.taps.index(pos1)
    assert adb.taps.index(pos1) < adb.taps.index(hero2_card)
    assert adb.taps.index(hero2_card) < adb.taps.index(pos2)


def test_spells_cast_at_scenario_positions(tmp_path):
    import json

    from coclab.strategy import Strategy

    data = json.loads(EXAMPLE.read_text())
    data["deploy_jitter_px"] = 0  # posisi spell persis; jitter diuji terpisah
    data["mirror_strategies"] = False
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))

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
    summary = run(load_config(p), "observe", 1, deps=deps)
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


def test_attack_uses_detected_card_positions(monkeypatch, tmp_path):
    """Kartu hasil deteksi template dipakai untuk deploy (bukan koordinat lama)."""
    import json

    from coclab import loop as loop_mod
    from coclab.strategy import Strategy

    data = json.loads(EXAMPLE.read_text())
    data["deploy_jitter_px"] = 0  # fokus presisi titik; jitter diuji terpisah
    data["mirror_strategies"] = False
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))

    detected = {
        "dragon": (170, 815, 0.90),
        "balloon": (291, 815, 0.90),
        "rage": (1180, 815, 0.90),
        "freeze": (1301, 815, 0.90),
        "hero_bk": (803, 815, 0.90),
        "hero_warden": (924, 815, 0.90),
        "hero_rc": (682, 815, 0.90),
        "hero_duke": (1050, 815, 0.90),
        "siege_blimp": (547, 815, 0.90),
    }
    monkeypatch.setattr(
        loop_mod.cards, "detect_cards", lambda img, tpl_dir, **kw: dict(detected)
    )
    strategy = Strategy(
        name="test",
        dragon_drops=[[0.5, 0.5]],
        balloon_drops=[[0.55, 0.5]],
        wall_wrecker_drop=[0.3, 0.55],
        hero_positions=[[0.6, 0.5]],
        rage_spell_positions=[[0.7, 0.5]],
        freeze_spell_positions=[[0.8, 0.5]],
    )
    deps, adb = make_deps(full_script(), [])
    deps.load_strategies = lambda path: [strategy]
    summary = run(load_config(p), "observe", 1, deps=deps)
    assert summary.ok

    def hit(x, y):
        return any(abs(tx - x) <= 2 and abs(ty - y) <= 2 for tx, ty in adb.taps)

    assert hit(170, 815)  # kartu dragon hasil deteksi
    assert hit(291, 815)  # balloon
    assert hit(547, 815)  # siege blimp
    assert hit(924, 815)  # warden (tap pusat kartu, jauh dari badge panah)
    assert hit(1050, 815)  # hero ke-4 (duke)
    assert hit(1180, 815)  # rage
    assert hit(1301, 815)  # freeze
    assert hit(800, 450)  # titik drop strategi tetap dipakai


def test_gate_strict_miss_ends_battle(monkeypatch):
    """rage/freeze strict hilang dari deteksi → end battle + tidak serang."""
    from coclab import loop as loop_mod
    from coclab.vision import Match
    monkeypatch.setattr(
        loop_mod.cards, "detect_cards",
        lambda img, tpl_dir, **kw: {"dragon": (170, 815, 0.9), "balloon": (291, 815, 0.9)},
    )
    states = []
    deps, adb = make_deps(full_script(), states)
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert (104, 675) in adb.taps  # end_battle_point (0.065, 0.75)
    assert "ATTACK" not in states or states.count("ATTACK") == 0


def test_gate_strict_pass_attacks(monkeypatch):
    from coclab import loop as loop_mod
    hits = {"dragon": (170, 815, 0.9), "balloon": (291, 815, 0.9),
            "rage": (1180, 815, 0.9), "freeze": (1301, 815, 0.9)}
    monkeypatch.setattr(loop_mod.cards, "detect_cards", lambda img, tpl_dir, **kw: dict(hits))
    states = []
    deps, adb = make_deps(full_script(), states)
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok and "ATTACK" in states
    assert (104, 675) not in adb.taps


def test_gate_verify_exception_falls_back(monkeypatch):
    """verify_deck melempar exception → fallback template lama, loop tetap jalan."""
    from coclab import loop as loop_mod

    monkeypatch.setattr(
        loop_mod.cards, "detect_cards",
        lambda img, tpl_dir, **kw: {"hero_bk": (803, 815, 0.9)},
    )

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(loop_mod.cards, "verify_deck", boom)
    states = []
    deps, adb = make_deps(full_script(), states)
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok and "ATTACK" in states


def test_deck_unknown_strict_type_logs_warning(tmp_path, monkeypatch, caplog):
    """Tipe strict tak dikenal tetap 'diabaikan' TAPI dicatat sebagai warning."""
    import json
    import logging

    from coclab import loop as loop_mod

    data = json.loads(EXAMPLE.read_text())
    data["deck_strict_types"] = ["dragon", "balloon", "wall_wrecker"]
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    hits = {"dragon": (170, 815, 0.9), "balloon": (291, 815, 0.9)}
    monkeypatch.setattr(
        loop_mod.cards, "detect_cards", lambda img, tpl_dir, **kw: dict(hits)
    )
    states = []
    deps, adb = make_deps(full_script(), states)
    with caplog.at_level(logging.WARNING, logger="coclab.loop"):
        summary = run(load_config(p), "observe", 1, deps=deps)
    assert summary.ok and "ATTACK" in states
    assert any(
        "tipe strict tak dikenal" in r.getMessage() for r in caplog.records
    )
    assert any("wall_wrecker" in r.getMessage() for r in caplog.records)


def _run_with_strategy(monkeypatch, tmp_config=None, strategy=None, script=None):
    from coclab.strategy import Strategy
    st = strategy or Strategy(
        name="t", dragon_drops=[[0.5, 0.5]], balloon_drops=[[0.55, 0.5]],
        wall_wrecker_drop=[0.3, 0.55], hero_positions=[[0.6, 0.5]],
        rage_spell_positions=[[0.7, 0.5]], freeze_spell_positions=[[0.8, 0.5]])
    states = []
    deps, adb = make_deps(script or full_script(), states)
    deps.load_strategies = lambda path: [st]
    cfg = load_config(tmp_config or EXAMPLE)
    summary = run(cfg, "observe", 1, deps=deps)
    return summary, adb, states


def test_jitter_applied_to_map_drops(tmp_path):
    import json
    data = json.loads(EXAMPLE.read_text())
    data["mirror_strategies"] = False  # fokus jitter; cermin diuji terpisah
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    summary, adb, _ = _run_with_strategy(None, tmp_config=p)
    assert summary.ok
    # dragon [0.5,0.5] → arah + (ke kanan) & ke atas: tx ∈ (800, 838], ty ∈ [423, 450)
    assert any(800 < tx <= 840 and 421 <= ty < 450 for tx, ty in adb.taps)
    # balloon [0.55,0.5] → arah − (ke tengah) & ke atas: tx ∈ [842, 880), ty ∈ [423, 450)
    assert any(842 <= tx < 880 and 421 <= ty < 450 for tx, ty in adb.taps)


def test_jitter_zero_taps_exact(tmp_path):
    import json
    data = json.loads(EXAMPLE.read_text())
    data["deploy_jitter_px"] = 0
    data["mirror_strategies"] = False
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    summary, adb, _ = _run_with_strategy(None, tmp_config=p)
    assert summary.ok
    assert (800, 450) in adb.taps      # dragon [0.5, 0.5] persis
    assert (880, 450) in adb.taps      # balloon [0.55, 0.5] persis


def test_zoom_out_before_attack_and_at_home():
    from coclab import pinch
    deps, adb = make_deps(full_script(), [])
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok
    sh = f"sh {pinch.REMOTE_PATH}"
    assert adb.shells.count(sh) >= 6  # 3x di find_attack (home) + 3x di attack()
    assert any(pinch.REMOTE_PATH in c and "cat >" in c for c in adb.shells)
    assert sum(1 for c in adb.shells if "cat >" in c) == 1  # skrip ditulis sekali (cache)


def test_zoom_out_disabled(tmp_path):
    import json
    data = json.loads(EXAMPLE.read_text())
    data["zoom_out_enabled"] = False
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    deps, adb = make_deps(full_script(), [])
    summary = run(load_config(p), "observe", 1, deps=deps)
    assert summary.ok
    assert not any("coclab_pinch_out.sh" in c for c in adb.shells)


def test_zoom_out_failure_never_breaks_loop():
    """Kegagalan pinch (mis. sendevent ditolak) ditelan: loop tetap jalan."""
    deps, adb = make_deps(full_script(), [])
    attempts = {"n": 0}

    def shell_fn(cmd):
        if "coclab_pinch_out.sh" in cmd:
            attempts["n"] += 1
            raise RuntimeError("sendevent ditolak")
        return "com.supercell.clashofclans" if "ps" in cmd else ""

    adb.shell_fn = shell_fn
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok
    assert attempts["n"] >= 2  # find_attack (home) + attack(): dua kegagalan, dua kali ditelan


def test_zoom_out_rewrites_script_after_run_failure():
    """Bila `sh` gagal (mis. skrip hilang pasca-reboot device), tulis ulang skrip."""
    from coclab import pinch
    from coclab.loop import _Session

    deps, adb = make_deps(full_script(), [])
    sh_cmd = f"sh {pinch.REMOTE_PATH}"
    writes = {"n": 0}
    runs = {"n": 0}

    def shell_fn(cmd):
        if cmd == sh_cmd:
            runs["n"] += 1
            if runs["n"] == 1:  # device reboot: skrip sudah tak ada
                raise RuntimeError("sh: not found")
        elif "cat >" in cmd and pinch.REMOTE_PATH in cmd:
            writes["n"] += 1
        return "com.supercell.clashofclans" if "ps" in cmd else ""

    adb.shell_fn = shell_fn
    session = _Session(load_config(EXAMPLE), "observe", deps)
    session.device = "127.0.0.1:5555"
    session.actions = deps.actions_factory(
        deps.adb, session.device, "observe", (1600, 900)
    )

    session._zoom_out()
    assert writes["n"] == 1
    assert session._pinch_ready is False  # kegagalan mereset cache

    session._zoom_out()
    assert writes["n"] == 2  # skrip ditulis ulang, bukan no-op selamanya
    assert session._pinch_ready is True


def test_mirror_picks_mirrored_scenario(monkeypatch):
    from coclab import loop as loop_mod
    from coclab.strategy import Strategy
    mirrored_dragon = [[0.1, 0.5]]
    st = Strategy(name="m", dragon_drops=mirrored_dragon, balloon_drops=[],
                  wall_wrecker_drop=None, hero_positions=[], rage_spell_positions=[],
                  freeze_spell_positions=[])
    monkeypatch.setattr(loop_mod.random, "choice", lambda seq: seq[-1])  # cermin di akhir
    summary, adb, _ = _run_with_strategy(None, strategy=st)
    assert summary.ok
    # asli [0.1] → cermin [0.9]: tx ∈ [1440−38, 1440]
    assert any(1402 <= tx <= 1441 and 421 <= ty <= 450 for tx, ty in adb.taps)


def test_find_attack_event_button_recognized():
    """Tombol Battle skin event (Treasure Hunt) dikenali saat attack.png tidak match."""
    from coclab.vision import Match

    script = full_script()
    del script["attack.png"]
    script["attack_event.png"] = Match(True, 92, 813, 0.95)
    states = []
    deps, adb = make_deps(script, states)
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok and "ATTACK" in states
    assert (92, 813) in adb.taps


def test_pause_gate_blocks_taps_until_resume():
    """Selama pause: nol tap; resume → siklus selesai dari titik yang sama."""
    deps, adb = make_deps(full_script(), [])
    paused = {"v": True}
    polls = {"n": 0}
    base_sleep = deps.sleep

    def spy_sleep(seconds):
        if paused["v"]:
            polls["n"] += 1
            if polls["n"] >= 3:
                paused["v"] = False  # pengguna menekan Resume setelah 3 poll
        base_sleep(seconds)

    deps.sleep = spy_sleep
    base_tap = adb.tap

    def trap_tap(device, x, y):
        assert not paused["v"], "tap dilakukan saat paused!"
        return base_tap(device, x, y)

    adb.tap = trap_tap
    summary = run(
        load_config(EXAMPLE), "observe", 1, deps=deps, is_paused=lambda: paused["v"]
    )
    assert summary.ok and polls["n"] >= 3


def test_dragon_badge_uses_detected_position():
    """Badge dragon dibaca dari kartu hasil deteksi; ROI tetap hanya fallback."""
    import numpy as np
    from coclab import vision
    from coclab.loop import _Session

    deps, _ = make_deps(full_script(), [])
    cfg = load_config(EXAMPLE)
    session = _Session(cfg, "observe", deps)
    session.deps.crop_percent = lambda im, *roi: vision.crop_percent(im, *roi)
    img = np.zeros((900, 1600, 3), np.uint8)
    shapes = []
    session.deps.read_badge = lambda crop: shapes.append(crop.shape) or 12

    val = session._dragon_badge_count(img, {"dragon": (291, 815, 0.9)})
    assert val == 12 and shapes and shapes[0][:2] == (30, 72)

    shapes.clear()
    val2 = session._dragon_badge_count(img, {})
    assert val2 == 12 and shapes and shapes[0][:2] == (54, 112)


def test_recover_rebuilds_then_rechecks_at_new_scout(monkeypatch, tmp_path):
    """Gate gagal → rebuild di menu → matchmaking lagi → gate dicek di scout BARU."""
    import json
    from coclab import loop as loop_mod

    data = json.loads(EXAMPLE.read_text())
    data["train_ui"] = {
        "army_button": [0.1125, 0.9478],
        "recipe_tab": [0.5, 0.1022],
        "recipe_use": [0.9338, 0.2589],
        "recipe_confirm": [0.6113, 0.6467],
        "close_button": [0.965, 0.0911],
    }
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))

    good = {
        "dragon": (291, 815, 0.9),
        "balloon": (170, 815, 0.9),
        "rage": (1180, 815, 0.9),
        "freeze": (1301, 815, 0.9),
    }
    seq = [dict(), dict(good)]

    def fake_detect(img, tpl_dir, **kw):
        return seq.pop(0) if seq else dict(good)

    monkeypatch.setattr(loop_mod.cards, "detect_cards", fake_detect)
    script = full_script()
    del script["dragon_card.png"]  # legacy fallback harus GAGAL di scout pertama
    del script["balloon_card.png"]
    states = []
    deps, adb = make_deps(script, states)
    summary = run(load_config(p), "observe", 1, deps=deps)
    assert summary.ok and "ATTACK" in states
    assert (104, 675) in adb.taps  # end battle saat gate pertama gagal
    # builder rutin per-siklus + builder RECOVER setelah end battle gate
    last_builder = len(adb.taps) - 1 - adb.taps[::-1].index((180, 853))
    assert last_builder > adb.taps.index((104, 675))
