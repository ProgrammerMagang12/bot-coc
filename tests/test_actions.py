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
