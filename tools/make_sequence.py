"""Kalibrasi URUTAN klik multi-layar (mis. latih pasukan).

    py tools/make_sequence.py --key train_points --device 127.0.0.1:5555 --config profiles/Shreyas.json

Alur pemakaian:
  1. Jalankan tool — layar game saat ini tampil
  2. Klik titik pertama (mis. tombol "Army / serangan" di layar home)
  3. Tekan N → navigasikan game ke layar berikutnya → tool screenshot ulang
  4. Klik titik berikutnya (mis. kartu resep pasukan), N lagi, klik "Train", N, klik "X/tutup"
  5. Tekan S untuk simpan (semua titik digabung berurutan)

Kontrol: klik=kumpulkan titik · N=layar berikutnya · Backspace=undo · S=simpan · Esc=batal
"""

from __future__ import annotations

import argparse
import json
import sys
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def capture_screen(device: str, config_path: Path, idx: int) -> Path:
    from coclab.adb import Adb
    from coclab.config import load_config

    adb_path = "adb"
    if config_path.is_file():
        adb_path = load_config(config_path).adb_path
    adb = Adb(adb_path)
    serial = adb.connect(device)
    dest = ROOT / "work" / f"seq_{idx}.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    adb.screencap(serial, str(dest))
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="make_sequence")
    parser.add_argument("--key", required=True, help="kunci config tujuan, mis. train_points")
    parser.add_argument("--device", default=None, help="adb address (capture otomatis per layar)")
    parser.add_argument("--image", default=None, help="file screenshot (mode statis)")
    parser.add_argument("--config", default="config.json")
    args = parser.parse_args(argv)
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path

    import cv2

    points: list[list[float]] = []
    screen_idx = [0]
    root = tk.Tk()
    root.title(f"GARUDA — kalibrasi urutan '{args.key}'")
    root.configure(bg="#14141f")
    canvas = tk.Canvas(root, highlightthickness=0)
    canvas.pack()
    hud = tk.Label(root, text="", bg="#14141f", fg="#ffb454", font=("Segoe UI", 10, "bold"))
    hud.pack(fill="x")
    photo_holder: list = []
    marks: list[int] = []
    size = [0, 0]

    def refresh_hud() -> None:
        hud.config(
            text=(
                f"layar {screen_idx[0] + 1} · {len(points)} titik  ·  klik=tambah  ·  "
                "N=layar berikutnya  ·  Backspace=undo  ·  S=simpan  ·  Esc=batal"
            )
        )

    def load_image(path: Path) -> None:
        img = cv2.imread(str(path))
        if img is None:
            return
        h, w = img.shape[:2]
        factor = min(1180 / w, 700 / h, 1.0)
        disp = (
            cv2.resize(img, None, fx=factor, fy=factor, interpolation=cv2.INTER_AREA)
            if factor < 1.0
            else img
        )
        dh, dw = disp.shape[:2]
        size[0], size[1] = dw, dh
        tmp = ROOT / "work" / "seq_disp.png"
        cv2.imwrite(str(tmp), disp)
        photo_holder.clear()
        photo_holder.append(tk.PhotoImage(file=str(tmp)))
        canvas.config(width=dw, height=dh)
        canvas.delete("all")
        canvas.create_image(0, 0, image=photo_holder[0], anchor="nw")
        for m in marks:
            canvas.delete(m)
        marks.clear()
        for i, (xp, yp) in enumerate(points):
            x, y = int(xp * dw), int(yp * dh)
            r = 6
            marks.append(
                canvas.create_oval(x - r, y - r, x + r, y + r, outline="#ffb454", width=2)
            )
            marks.append(
                canvas.create_text(
                    x, y - 14, text=str(i + 1), fill="#ffb454", font=("Segoe UI", 8, "bold")
                )
            )
        refresh_hud()

    def on_click(event) -> None:
        dw, dh = size
        if dw <= 0 or event.x > dw or event.y > dh or event.x < 0 or event.y < 0:
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

    def on_next(_event=None) -> None:
        if args.image:
            load_image(Path(args.image))
            return
        if args.device:
            screen_idx[0] += 1
            print(f"screenshot layar {screen_idx[0] + 1}...")
            load_image(capture_screen(args.device, config_path, screen_idx[0]))

    def on_undo(_event=None) -> None:
        if points:
            points.pop()
            refresh_hud()

    def on_save(_event=None) -> None:
        if not points:
            print("tidak ada titik; tidak menyimpan")
            root.destroy()
            return
        data = {}
        if config_path.is_file():
            data = json.loads(config_path.read_text(encoding="utf-8"))
        data[args.key] = points
        config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"tersimpan {len(points)} titik ke '{args.key}' di {config_path}")
        root.destroy()

    canvas.bind("<Button-1>", on_click)
    root.bind("<n>", on_next)
    root.bind("<N>", on_next)
    root.bind("<BackSpace>", on_undo)
    root.bind("<s>", on_save)
    root.bind("<S>", on_save)
    root.bind("<Escape>", lambda _e: root.destroy())

    if args.image:
        load_image(Path(args.image))
    elif args.device:
        load_image(capture_screen(args.device, config_path, 0))
    else:
        print("wajib --device atau --image")
        return 1
    refresh_hud()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
