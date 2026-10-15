"""Pinch-out gesture built from raw ``sendevent`` writes (pure strings, no I/O).

The camera in CoC can end up zoomed in (accidental pinch), which makes troops
undeployable outside the visible village. A two-finger pinch-close (fingers
converging vertically) zoom-outs the camera to max in ~0.5 s and is idempotent
when already zoomed out.

Constants and the sequence come from the live spike on LDPlayer (1600x900):
``/dev/input/event4`` is writable without root (``adb shell`` is in the
``input`` group) and its ABS_MT axes are 1:1 with the screen.
"""

from __future__ import annotations

TOUCH_DEVICE = "/dev/input/event4"
REMOTE_PATH = "/data/local/tmp/coclab_pinch_out.sh"

# Kernel input codes (include/uapi/linux/input-event-codes.h).
EV_SYN = 0
EV_KEY = 1
EV_ABS = 3
SYN_REPORT = 0
BTN_TOUCH = 330
ABS_MT_SLOT = 47
ABS_MT_TRACKING_ID = 57
ABS_MT_POSITION_X = 53
ABS_MT_POSITION_Y = 54

_FINGER_0_TRACKING_ID = 100
_FINGER_1_TRACKING_ID = 101
_GAP_START = 150  # jarak tiap jari dari pusat layar saat turun
_GAP_END = 40  # jarak akhir: jari saling mendekat → kamera zoom out
_DOWN_SLEEP_S = 0.12
_STEP_SLEEP_S = 0.06


def build_pinch_out_script(
    width: int = 1600,
    height: int = 900,
    steps: int = 5,
    device: str = TOUCH_DEVICE,
) -> str:
    """Shell script (sendevent) for a vertical two-finger pinch-close.

    Finger 0 starts at ``(cx, cy-150)`` and finger 1 at ``(cx, cy+150)``; both
    converge to ``cy-40`` / ``cy+40`` over ``steps`` moves. Ends with the
    tracking-id release of both slots, ``BTN_TOUCH`` up and a final ``SYN``.
    """
    cx = width // 2
    cy = height // 2
    top_start, top_end = cy - _GAP_START, cy - _GAP_END
    bottom_start, bottom_end = cy + _GAP_START, cy + _GAP_END
    lines: list[str] = []

    def se(ev_type: int, code: int, value: int) -> None:
        lines.append(f"sendevent {device} {ev_type} {code} {value}")

    # Dua jari turun bersamaan: slot 0 (atas) lalu slot 1 (bawah).
    se(EV_ABS, ABS_MT_SLOT, 0)
    se(EV_ABS, ABS_MT_TRACKING_ID, _FINGER_0_TRACKING_ID)
    se(EV_ABS, ABS_MT_POSITION_X, cx)
    se(EV_ABS, ABS_MT_POSITION_Y, top_start)
    se(EV_ABS, ABS_MT_SLOT, 1)
    se(EV_ABS, ABS_MT_TRACKING_ID, _FINGER_1_TRACKING_ID)
    se(EV_ABS, ABS_MT_POSITION_X, cx)
    se(EV_ABS, ABS_MT_POSITION_Y, bottom_start)
    se(EV_KEY, BTN_TOUCH, 1)
    se(EV_SYN, SYN_REPORT, 0)
    lines.append(f"sleep {_DOWN_SLEEP_S}")

    # Gerakan bertahap: tiap langkah menggeser kedua jari sedikit ke pusat.
    total = max(int(steps), 1)
    for index in range(1, total + 1):
        t = index / total
        top = int(top_start + (top_end - top_start) * t)
        bottom = int(bottom_start + (bottom_end - bottom_start) * t)
        se(EV_ABS, ABS_MT_SLOT, 0)
        se(EV_ABS, ABS_MT_POSITION_Y, top)
        se(EV_ABS, ABS_MT_SLOT, 1)
        se(EV_ABS, ABS_MT_POSITION_Y, bottom)
        se(EV_SYN, SYN_REPORT, 0)
        lines.append(f"sleep {_STEP_SLEEP_S}")

    # Jari naik: lepas tracking kedua slot lalu BTN_TOUCH up.
    se(EV_ABS, ABS_MT_SLOT, 0)
    se(EV_ABS, ABS_MT_TRACKING_ID, -1)
    se(EV_ABS, ABS_MT_SLOT, 1)
    se(EV_ABS, ABS_MT_TRACKING_ID, -1)
    se(EV_KEY, BTN_TOUCH, 0)
    se(EV_SYN, SYN_REPORT, 0)
    return "\n".join(lines) + "\n"


def write_script_cmd(path: str = REMOTE_PATH, script: str | None = None) -> str:
    """Single ``adb shell`` command that writes the script via heredoc + chmod.

    The script body contains no single quotes, so the quoted ``COCLAB_EOF``
    delimiter is safe.
    """
    body = build_pinch_out_script() if script is None else script
    if not body.endswith("\n"):
        body += "\n"
    return f"cat > {path} << 'COCLAB_EOF'\n{body}COCLAB_EOF\nchmod 755 {path}"
