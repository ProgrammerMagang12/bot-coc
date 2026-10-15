"""Kalibrasi titik kolektor (gold mine / elixir pump / DE drill / loot cart).

    py tools/make_collect.py --device 127.0.0.1:5555
    py tools/make_collect.py --image work/home.png --config profiles/Shreyas.json

Klik tiap kolektor. Tap di kolektor = collect (tanpa UI), jadi titik harus tepat.
Kontrol: Backspace = hapus terakhir · S = simpan · Esc = batal.
"""

from __future__ import annotations

import argparse
import json
import sys
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def capture_screen(device: str, config_path: Path) -> Path:
    from coclab.adb import Adb
    from coclab.config import load_config

    adb_path = "adb"
    if config_path.is_file():
        adb_path = load_config(config_path).adb_path
    adb = Adb(adb_path)
    serial = adb.connect(device)
    dest = ROOT / "work" / "collect_home.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    adb.screencap(serial, str(dest))
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="make_collect")
    parser.add_argument("--device", default=None, help="adb address (screencap otomatis)")
    parser.add_argument("--image", default=None, help="pakai file screenshot")
    parser.add_argument("--config", default="config.json", help="file config/profil target")
    args = parser.parse_args(argv)
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path

    if args.image:
        image_path = Path(args.image)
    elif args.device:
        image_path = capture_screen(args.device, config_path)
        print("screenshot:", image_path)
    else:
        print("wajib --device atau --image")
        return 1

    import cv2

    img = cv2.imread(str(image_path))
    if img is None:
        print("gagal membaca:", image_path)
        return 1
    h, w = img.shape[:2]
    factor = min(1180 / w, 700 / h, 1.0)
    disp = (
        cv2.resize(img, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
        if factor < 1.0
        else img
    )
    dh, dw = disp.shape[:2]
    tmp = ROOT / "work" / "collect_disp.png"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(tmp), disp)

    points: list[list[float]] = []
    root = tk.Tk()
    root.title("GARUDA — kalibrasi titik kolektor")
    root.configure(bg="#14141f")
    canvas = tk.Canvas(root, width=dw, height=dh, highlightthickness=0)
    canvas.pack()
    photo = tk.PhotoImage(file=str(tmp))
    canvas.create_image(0, 0, image=photo, anchor="nw")
    hud = tk.Label(root, text="", bg="#14141f", fg="#ffb454", font=("Segoe UI", 10, "bold"))
    hud.pack(fill="x")

    marks: list[int] = []

    def refresh_hud() -> None:
        hud.config(
            text=f"{len(points)} titik  ·  klik=kolektor  ·  Backspace=undo  ·  S=simpan  ·  Esc=batal"
        )

    def on_click(event) -> None:
        if event.x > dw or event.y > dh or event.y < 0 or event.x < 0:
            return
        points.append([round(event.x / dw, 4), round(event.y / dh, 4)])
        r = 6
        marks.append(
            canvas.create_oval(
                event.x - r, event.y - r, event.x + r, event.y + r, outline="#ffb454", width=2
            )
        )
        marks.append(
            canvas.create_text(
                event.x, event.y - 14, text=str(len(points)), fill="#ffb454",
                font=("Segoe UI", 8, "bold"),
            )
        )
        refresh_hud()

    def on_undo(_event=None) -> None:
        if points:
            points.pop()
            canvas.delete(marks.pop())
            canvas.delete(marks.pop())
            refresh_hud()

    def on_save(_event=None) -> None:
        data = {}
        if config_path.is_file():
            data = json.loads(config_path.read_text(encoding="utf-8"))
        data["collect_points"] = points
        config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"tersimpan {len(points)} titik ke {config_path}")
        root.destroy()

    canvas.bind("<Button-1>", on_click)
    root.bind("<BackSpace>", on_undo)
    root.bind("<s>", on_save)
    root.bind("<S>", on_save)
    root.bind("<Escape>", lambda _e: root.destroy())
    refresh_hud()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
