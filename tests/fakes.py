import numpy as np

from pathlib import Path

from coclab.loop import Deps
from coclab.vision import Match


class RecordingAdb:
    def __init__(self):
        self.taps = []
        self.swipes = []
        self.connected = None

    def connect(self, addr):
        self.connected = addr
        return addr

    def wm_size(self, device):
        return 1600, 900

    def tap(self, d, x, y):
        self.taps.append((x, y))

    def swipe(self, d, x1, y1, x2, y2):
        self.swipes.append((x1, y1, x2, y2))


class FakeActions:
    def __init__(self, adb, device, mode, screen):
        self.adb, self.device = adb, device

    def tap_percent(self, xp, yp):
        self.adb.tap(self.device, int(xp * 1600), int(yp * 900))

    def tap_px(self, x, y):
        self.adb.tap(self.device, x, y)

    def swipe_percent(self, x1p, y1p, x2p, y2p):
        self.adb.swipe(
            self.device,
            int(x1p * 1600),
            int(y1p * 900),
            int(x2p * 1600),
            int(y2p * 900),
        )


def make_deps(script, states):
    """script: {nama_template: Match}. fake find_template membaca Path(tpl).name."""

    def find_template(img, tpl, threshold):
        return script.get(Path(tpl).name, Match(False, 0, 0, 0.0))

    deps = Deps(
        adb=RecordingAdb(),
        capture_fn=lambda adb_, dev, dest, retries=2: True,
        load_image=lambda p: np.zeros((10, 10, 3), np.uint8),
        find_template=find_template,
        crop_percent=lambda img, *a: img,
        ocr_digits=lambda img, engine=None: 999999,
        actions_factory=lambda a, d, m, s: FakeActions(a, d, m, s),
        load_strategies=lambda path: [],
        sleep=lambda s: None,
        monotonic=lambda: 0.0,
        state_hook=lambda st: states.append(st),
    )
    return deps, deps.adb


def full_script(**overrides):
    base = {
        "attack.png": Match(True, 1, 1, 0.95),
        "find_match.png": Match(True, 1, 1, 0.95),
        "attack2.png": Match(True, 600, 700, 0.95),
        "next.png": Match(True, 1400, 640, 0.95),
        "returnhome.png": Match(True, 1, 1, 0.95),
    }
    base.update(overrides)
    return base
