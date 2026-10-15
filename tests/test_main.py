import main as cli


def test_defaults_are_observe_cycles_1():
    a = cli.build_parser().parse_args([])
    assert a.live is False and a.cycles == 1 and a.config == "config.json"


def test_live_flag_and_cycles():
    a = cli.build_parser().parse_args(["--live", "--cycles", "2"])
    assert a.live is True and a.cycles == 2


def test_main_maps_mode_and_exit_code(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        cli,
        "_run_loop",
        lambda cfg, mode, cycles: captured.update(mode=mode, cycles=cycles)
        or type("S", (), {"ok": True, "reason": "", "cycles_done": 1})(),
    )
    assert cli.main(["--live", "--cycles", "1", "--config", "config.example.json"]) == 0
    assert captured == {"mode": "live", "cycles": 1}


def test_keyboard_interrupt_returns_130(monkeypatch):
    def boom(*_a, **_k):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_run_loop", boom)
    assert cli.main(["--config", "config.example.json"]) == 130  # Review Focus #5


def test_missing_config_returns_1(monkeypatch, capsys):
    assert cli.main(["--config", "tidak-ada.json"]) == 1
    assert "config.example.json" in capsys.readouterr().err  # Review Focus #3


def test_observe_flag_is_accepted():
    a = cli.build_parser().parse_args(["--observe"])
    assert a.live is False and a.observe is True


def test_observe_and_live_are_mutually_exclusive():
    import pytest

    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["--observe", "--live"])


def test_main_default_mode_is_observe(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        cli,
        "_run_loop",
        lambda cfg, mode, cycles: captured.update(mode=mode)
        or type("S", (), {"ok": True, "reason": "", "cycles_done": 1})(),
    )
    assert cli.main(["--config", "config.example.json"]) == 0
    assert captured["mode"] == "observe"
