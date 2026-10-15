from coclab import capture as cap


def test_retries_until_valid(tmp_path):
    calls = []

    def write_png(dest):
        import cv2
        import numpy as np

        cv2.imwrite(str(dest), np.zeros((10, 10, 3), np.uint8))

    class A:
        def screencap(self, d, dest):
            calls.append(1)
            if len(calls) >= 2:
                write_png(dest)  # PNG asli pada percobaan kedua
            else:
                dest.write_bytes(b"")  # kosong: tidak valid

    ok = cap.capture(A(), "dev", tmp_path / "s.png", retries=2, sleep=lambda _s: None)
    assert ok and len(calls) == 2


def test_all_attempts_invalid_returns_false(tmp_path):
    class A:
        def screencap(self, d, dest):
            dest.write_bytes(b"")

    assert cap.capture(A(), "dev", tmp_path / "s.png", retries=2, sleep=lambda _s: None) is False


def test_screencap_exception_is_retried(tmp_path, monkeypatch):
    seq = iter([RuntimeError("pull failed"), None])

    class A:
        def screencap(self, d, dest):
            item = next(seq)
            if item:
                raise item
            import cv2
            import numpy as np

            cv2.imwrite(str(dest), np.zeros((10, 10, 3), np.uint8))

    assert cap.capture(A(), "dev", tmp_path / "s.png", retries=2, sleep=lambda _s: None) is True
