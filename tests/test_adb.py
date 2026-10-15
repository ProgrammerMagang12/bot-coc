import pytest

from pathlib import Path

from coclab.adb import Adb, AdbError


class FakeRunner:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def __call__(self, args):
        self.calls.append(args)
        return self.responses.pop(0)


def test_connect_returns_matching_serial():
    r = FakeRunner(
        [
            (0, b"connected to 127.0.0.1:5555\n", ""),
            (0, b"List of devices attached\n127.0.0.1:5555\tdevice\n", ""),
        ]
    )
    a = Adb("adb.exe", r)
    assert a.connect("127.0.0.1:5555") == "127.0.0.1:5555"
    assert r.calls[0] == ["adb.exe", "connect", "127.0.0.1:5555"]


def test_wm_size_prefers_override_then_physical_then_fallback():
    out = b"Physical size: 1080x1920\nOverride size: 720x1280\n"
    r = FakeRunner(
        [(0, b"List of devices attached\n127.0.0.1:5555\tdevice\n", ""), (0, out, "")]
    )
    a = Adb("adb.exe", r)
    assert a.wm_size("127.0.0.1:5555") == (720, 1280)

    r2 = FakeRunner(
        [
            (0, b"List of devices attached\n127.0.0.1:5555\tdevice\n", ""),
            (0, b"Physical size: 1080x1920\n", ""),
        ]
    )
    assert Adb("adb.exe", r2).wm_size("127.0.0.1:5555") == (1080, 1920)

    r3 = FakeRunner(
        [
            (0, b"List of devices attached\n127.0.0.1:5555\tdevice\n", ""),
            (0, b"garbage\n", ""),
        ]
    )
    assert Adb("adb.exe", r3).wm_size("127.0.0.1:5555") == (1600, 900)


def test_tap_uses_shell_input_tap_args():
    r = FakeRunner(
        [(0, b"List of devices attached\n127.0.0.1:5555\tdevice\n", ""), (0, b"", "")]
    )
    Adb("adb.exe", r).tap("127.0.0.1:5555", 12, 34)
    assert r.calls[1] == [
        "adb.exe",
        "-s",
        "127.0.0.1:5555",
        "shell",
        "input",
        "tap",
        "12",
        "34",
    ]


def test_screencap_writes_bytes(tmp_path):
    r = FakeRunner(
        [
            (0, b"List of devices attached\n127.0.0.1:5555\tdevice\n", ""),
            (0, b"PNGDATA", ""),
        ]
    )
    dest = tmp_path / "s.png"
    Adb("adb.exe", r).screencap("127.0.0.1:5555", dest)
    assert dest.read_bytes() == b"PNGDATA"


def test_missing_adb_binary_is_clear_error():
    def boom(_args):
        raise FileNotFoundError("adb.exe")

    with pytest.raises(AdbError, match="adb"):
        Adb("nope/adb.exe", boom).devices()  # Review Focus #1


def test_connect_fails_when_device_not_listed():
    r = FakeRunner([(0, b"cannot connect\n", ""), (0, b"List of devices attached\n", "")])
    with pytest.raises(AdbError, match="not online|not listed"):
        Adb("adb.exe", r).connect("127.0.0.1:5555")
