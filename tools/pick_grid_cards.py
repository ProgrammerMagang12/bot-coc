"""Kalibrasi 6 kartu grid Deck Builder — SIMPEL 6 langkah.

    py tools/pick_grid_cards.py --device 127.0.0.1:5555 --config dist\\GARUDA\\profiles\\Shreyas.json

Alur: ikuti teks kuning di jendela tool. Klik titik yang diminta di gambar,
lalu tekan N (screenshot baru) untuk lanjut. Tekan S di akhir untuk simpan.
"""

from __future__ import annotations

import argparse
import json
import sys
import tkinter as tk
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

STEPS: list[tuple[str, str]] = [
    (
        "grid.dragon_drops",
        "Di game: Attack (kiri-bawah) -> Edit Army -> tap SEMBARANG slot pasukan "
        "(daftar troop terbuka di bawah) -> KLIK KARTU DRAGON (ungu, lvl 12). Lalu tekan N",
    ),
    ("grid.balloon_drops", "KLIK KARTU BALLOON (balon kerangka/skull). Lalu tekan N"),
    ("grid.extra_troop", "KLIK KARTU EXTRA kamu (yang dipakai x2). Lalu tekan N"),
    (
        "grid.wall_wrecker_drop",
        "Navigasi: tap slot SIEGE (baris kanan '3/3') sampai daftar siege terbuka -> "
        "KLIK KARTU SIEGE kamu. Lalu tekan N",
    ),
    (
        "grid.rage_spell",
        "Navigasi: tutup daftar siege, tap slot SPELL (baris '11/11') -> daftar spell terbuka "
        "-> KLIK RAGE (botol ungu). Lalu tekan N",
    ),
    ("grid.freeze_spell", "KLIK FREEZE (biru/putih). Tekan S untuk SIMPAN"),
]


def capture_screen(device: str, config_path: Path, idx: int) -> Path:
    from coclab.adb import Adb
    from coclab.config import load_config

    adb_path = "adb"
    if config_path.is_file():
        try:
            adb_path = load_config(config_path).adb_path
        except Exception:  # noqa: BLE001
            pass
    adb = Adb(adb_path)
    serial = adb.connect(device)
    dest = ROOT / "work" / f"gridpick_{idx}.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    adb.screencap(serial, str(dest))
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pick_grid_cards")
    parser.add_argument("--device", default="127.0.0.1:5555")
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path

    import cv2

    step = [0]
    result: dict[str, list[float]] = {}
    shot = [0]
    root = tk.Tk()
    root.title("GARUDA — pilih 6 kartu grid (simplified)")
    root.configure(bg="#14141f")
    hud = tk.Label(
        root, text="", bg="#14141f", fg="#ffb454", font=("Segoe UI", 11, "bold"),
        wraplength=1180, justify="left",
    )
    hud.pack(fill="x", padx=8, pady=4)
    canvas = tk.Canvas(root, highlightthickness=0)
    canvas.pack()
    photo: list = []
    size = [0, 0]

    def refresh() -> None:
        if step[0] >= len(STEPS):
            hud.config(text="SELESAI! Tekan S untuk simpan (Backspace=undo, Esc=batal)")
            return
        key, prompt = STEPS[step[0]]
        status = "OK tercatat" if key in result else "belum diklik"
        hud.config(text=f"LANGKAH {step[0] + 1}/{len(STEPS)}  [{status}]  {prompt}")

    def load(path: Path) -> None:
        img = cv2.imread(str(path))
        if img is None:
            return
        h, w = img.shape[:2]
        f = min(1180 / w, 600 / h, 1.0)
        disp = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA) if f < 1 else img
        dh, dw = disp.shape[:2]
        size[0], size[1] = dw, dh
        tmp = ROOT / "work" / "gridpick_disp.png"
        cv2.imwrite(str(tmp), disp)
        photo.clear()
        photo.append(tk.PhotoImage(file=str(tmp)))
        canvas.config(width=dw, height=dh)
        canvas.delete("all")
        canvas.create_image(0, 0, image=photo[0], anchor="nw")
        for key, (xp, yp) in result.items():
            x, y = int(xp * dw), int(yp * dh)
            canvas.create_oval(x - 7, y - 7, x + 7, y + 7, outline="#2ecc71", width=2)
            canvas.create_text(x, y - 15, text=key.split(".")[-1][:8], fill="#2ecc71",
                               font=("Segoe UI", 8, "bold"))

    def on_click(event) -> None:
        dw, dh = size
        if step[0] >= len(STEPS) or dw <= 0 or event.x > dw or event.y > dh:
            return
        key = STEPS[step[0]][0]
        result[key] = [round(event.x / dw, 4), round(event.y / dh, 4)]
        load(Path(ROOT / "work" / "gridpick_disp.png"))
        refresh()

    def on_next(_event=None) -> None:
        if step[0] < len(STEPS):
            step[0] += 1
        shot[0] += 1
        print("screenshot layar berikutnya...")
        load(capture_screen(args.device, config_path, shot[0]))
        refresh()

    def on_undo(_event=None) -> None:
        if result:
            result.popitem()
            refresh()

    def on_save(_event=None) -> None:
        data = json.loads(config_path.read_text(encoding="utf-8")) if config_path.is_file() else {}
        ui = data.get("train_ui") or {}
        grid = {**(ui.get("grid") or {})}
        for key, point in result.items():
            grid[key.split(".", 1)[1]] = point
        ui["grid"] = grid
        data["train_ui"] = ui
        config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"tersimpan {len(result)} kartu ke train_ui.grid di {config_path}")
        root.destroy()

    canvas.bind("<Button-1>", on_click)
    root.bind("<n>", on_next)
    root.bind("<N>", on_next)
    root.bind("<BackSpace>", on_undo)
    root.bind("<s>", on_save)
    root.bind("<S>", on_save)
    root.bind("<Escape>", lambda _e: root.destroy())
    load(capture_screen(args.device, config_path, 0))
    refresh()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
