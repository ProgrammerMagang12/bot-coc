from coclab.actions import Actions


class RecordingAdb:
    def __init__(self):
        self.taps = []

    def tap(self, device, x, y):
        self.taps.append((device, x, y))


def test_live_taps_convert_percent_to_pixels():
    adb = RecordingAdb()
    a = Actions(adb, "dev", "live", (1600, 900))
    a.tap_percent(0.25, 0.5)
    assert adb.taps == [("dev", 400, 450)]


def test_observe_never_touches_adb(caplog):
    import logging

    caplog.set_level(logging.INFO, logger="coclab.actions")
    adb = RecordingAdb()
    a = Actions(adb, "dev", "observe", (1600, 900))
    a.tap_percent(0.25, 0.5)
    a.tap_px(10, 20)
    assert adb.taps == []  # gerbang observe
    assert any("[OBSERVE]" in r.message for r in caplog.records)


class RecordingAdbSwipe:
    def __init__(self):
        self.swipes = []

    def swipe(self, device, x1, y1, x2, y2, duration_ms=300):
        self.swipes.append((device, x1, y1, x2, y2, duration_ms))


def test_live_swipe_percent_converts():
    adb = RecordingAdbSwipe()
    a = Actions(adb, "dev", "live", (1600, 900))
    a.swipe_percent(0.25, 0.7, 0.25, 0.3)
    assert adb.swipes == [("dev", 400, 630, 400, 270, 300)]


def test_live_swipe_percent_passes_duration():
    adb = RecordingAdbSwipe()
    a = Actions(adb, "dev", "live", (1600, 900))
    a.swipe_percent(0.1, 0.9, 0.3, 0.5, duration_ms=800)
    assert adb.swipes == [("dev", 160, 810, 480, 450, 800)]


def test_observe_swipe_only_logs(caplog):
    import logging

    caplog.set_level(logging.INFO, logger="coclab.actions")
    adb = RecordingAdbSwipe()
    a = Actions(adb, "dev", "observe", (1600, 900))
    a.swipe_percent(0.25, 0.7, 0.25, 0.3)
    assert adb.swipes == []
    assert any("[OBSERVE]" in r.message for r in caplog.records)
