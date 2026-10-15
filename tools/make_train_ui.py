"""Kalibrasi terpandu untuk Deck Builder (train_ui).

    py tools/make_train_ui.py --device 127.0.0.1:5555 --config dist\\GARUDA\\profiles\\Shreyas.json

Alur: setiap langkah punya instruksi di jendela tool.
  - KLIK titik yang diminta di layar (tercatat untuk langkah itu)
  - Tekan N = screenshot ulang / lanjut langkah berikutnya (lewati jika tidak ada)
  - Setelah semua langkah langkah, tekan S untuk simpan
Kontrol: klik=catat · N=lanjut · Backspace=hapus titik terakhir (langkah terakhir) · S=simpan · Esc=batal
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
    ("army_button", "Di HOME: KLIK tombol Army / latih pasukan (untuk buka panel My Army)"),
    ("clear_troops", "Di panel: KLIK ikon tempat sampah (clear) bagian PASUKAN  (N = tidak ada)"),
    ("clear_confirm", "KLIK tombol konfirmasi (Remove/OK) kalau muncul  (N = tidak ada)"),
    ("clear_spells", "KLIK ikon clear bagian SPELL  (N = tidak ada)"),
    ("clear_siege", "KLIK ikon clear bagian SIEGE  (N = tidak ada)"),
    ("grid.dragon_drops", "Buka daftar pilih troop (tap slot), lalu KLIK kartu DRAGON"),
    ("grid.balloon_drops", "KLIK kartu BALLOON di daftar"),
    ("grid.wall_wrecker_drop", "KLIK kartu SIEGE (wall wrecker/battle machine) di daftar"),
    ("grid.extra_troop", "KLIK kartu EXTRA TROOP (apprentice warden/archer dst) di daftar"),
    ("grid.rage_spell", "Pindah ke daftar SPELL, lalu KLIK kartu RAGE"),
    ("grid.freeze_spell", "KLIK kartu FREEZE"),
    ("close_button", "KLIK tombol X / tutup panel My Army"),
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
    dest = ROOT / "work" / f"trainui_{idx}.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    adb.screencap(serial, str(dest))
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="make_train_ui")
    parser.add_argument("--device", default=None)
    parser.add_argument("--image", default=None, help="mode statis (hanya untuk tes)")
    parser.add_argument("--config", required=True, help="file profil/config target")
    args = parser.parse_args(argv)
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path

    import cv2

    step_idx = [0]
    result: dict[str, list[float]] = {}
    record: list[tuple[str, list[float]]] = []
    shot_idx = [0]
    root = tk.Tk()
    root.title("GARUDA — Deck Builder: kalibrasi terpandu")
    root.configure(bg="#14141f")
    canvas = tk.Canvas(root, highlightthickness=0)
    canvas.pack()
    hud = tk.Label(root, text="", bg="#14141f", fg="#ffb454", font=("Segoe UI", 10, "bold"))
    hud.pack(fill="x")
    photo_holder: list = []
    size = [0, 0]

    def refresh_hud() -> None:
        if step_idx[0] >= len(STEPS):
            hud.config(text="SEMUA LANGKAH SELESAI — tekan S untuk simpan · Backspace=undo · Esc=batal")
            return
        key, prompt = STEPS[step_idx[0]]
        status = "✓ tercatat" if key in result else "…"
        hud.config(
            text=f"Langkah {step_idx[0] + 1}/{len(STEPS)} [{key}] {status}  ·  {prompt}  (N=lanjut)"
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
        tmp = ROOT / "work" / "trainui_disp.png"
        cv2.imwrite(str(tmp), disp)
        photo_holder.clear()
        photo_holder.append(tk.PhotoImage(file=str(tmp)))
        canvas.config(width=dw, height=dh)
        canvas.delete("all")
        canvas.create_image(0, 0, image=photo_holder[0], anchor="nw")
        for key, (xp, yp) in record:
            x, y = int(xp * dw), int(yp * dh)
            r = 6
            canvas.create_oval(x - r, y - r, x + r, y + r, outline="#ffb454", width=2)
            canvas.create_text(
                x, y - 13, text=key.split(".")[-1][:6], fill="#ffb454", font=("Segoe UI", 7, "bold")
            )

    def on_click(event) -> None:
        dw, dh = size
        if step_idx[0] >= len(STEPS) or dw <= 0:
            return
        if event.x > dw or event.y > dh or event.x < 0 or event.y < 0:
            return
        key = STEPS[step_idx[0]][0]
        point = [round(event.x / dw, 4), round(event.y / dh, 4)]
        result[key] = point
        record.append((key, point))
        refresh_hud()

    def on_next(_event=None) -> None:
        if step_idx[0] < len(STEPS):
            step_idx[0] += 1
        if args.device:
            shot_idx[0] += 1
            print("screenshot layar berikutnya...")
            load_image(capture_screen(args.device, config_path, shot_idx[0]))
        refresh_hud()

    def on_undo(_event=None) -> None:
        if record:
            key, _point = record.pop()
            result.pop(key, None)
            load_image(Path(ROOT / "work" / "trainui_disp.png"))
            refresh_hud()

    def on_save(_event=None) -> None:
        data: dict = {}
        if config_path.is_file():
            data = json.loads(config_path.read_text(encoding="utf-8"))
        ui: dict = {}
        grid: dict = {}
        for key, point in result.items():
            if key.startswith("grid."):
                grid[key.split(".", 1)[1]] = point
            else:
                ui[key] = point
        if grid:
            ui["grid"] = grid
        data["train_ui"] = ui
        config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"tersimpan {len(result)} titik ke train_ui di {config_path}")
        for key in sorted(result):
            print("  -", key)
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
