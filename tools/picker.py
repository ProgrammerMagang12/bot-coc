"""Tkinter picker GUI for strategy points and template crops (coc-lab).

Usage:
    # strategi: klik titik drop, d/b/w ganti grup, klik-kanan/u undo, s simpan
    py tools/picker.py --image work/dev/scout.png --mode strategy --name Malam2

    # template: drag kotak pada screenshot, s simpan ke assets/<nama>.png
    py tools/picker.py --image work/dev/shot.png --mode template --name attack
"""

from __future__ import annotations

import argparse
import sys
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageTk

sys.path.insert(0, str(Path(__file__).parent))
from make_strategy import points_to_percent, save_strategy  # noqa: E402
from make_template import crop_and_save, region_percent  # noqa: E402

MAX_W, MAX_H = 1280, 700
GROUP_COLORS = {
    "dragon": "#e53935",
    "balloon": "#43a047",
    "wall_wrecker": "#fb8c00",
}
GROUP_KEYS = {"d": "dragon", "b": "balloon", "w": "wall_wrecker"}


def scale_factor(img_w: int, img_h: int, max_w: int = MAX_W, max_h: int = MAX_H) -> float:
    """Fit factor in (0, 1]: shrink only when the image is too large."""
    return min(1.0, max_w / img_w, max_h / img_h)


def display_to_image(x: int, y: int, scale: float) -> tuple[int, int]:
    """Convert display coordinates to image coordinates (guards scale <= 0)."""
    if scale <= 0:
        return x, y
    return int(x / scale), int(y / scale)


class PickerApp:
    def __init__(
        self,
        root: tk.Tk,
        image_path: str,
        mode: str,
        name: str,
        out_path: str,
        assets_dir: str,
    ) -> None:
        self.root = root
        self.image_path = image_path
        self.mode = mode
        self.name = name
        self.out_path = out_path
        self.assets_dir = assets_dir

        self.image = Image.open(image_path).convert("RGB")
        self.scale = scale_factor(self.image.width, self.image.height)
        disp_size = (
            int(self.image.width * self.scale),
            int(self.image.height * self.scale),
        )
        self.disp_image = ImageTk.PhotoImage(self.image.resize(disp_size))

        root.title(f"coc-lab picker [{mode}] — {Path(image_path).name} → {name}")
        self.canvas = tk.Canvas(
            root, width=disp_size[0], height=disp_size[1], cursor="crosshair"
        )
        self.canvas.pack(side=tk.TOP)
        self.status = tk.Label(root, anchor="w", font=("Consolas", 11), justify=tk.LEFT)
        self.status.pack(side=tk.TOP, fill=tk.X)
        buttons = tk.Frame(root)
        buttons.pack(side=tk.TOP, fill=tk.X)

        self.groups: dict[str, list[tuple[int, int]]] = {key: [] for key in GROUP_COLORS}
        self.active = "dragon"
        self.drag_start: tuple[int, int] | None = None
        self.rect_id = None
        self.selection: tuple[int, int, int, int] | None = None

        if mode == "strategy":
            for key, label in (
                ("dragon", "Dragon (d)"),
                ("balloon", "Balloon (b)"),
                ("wall_wrecker", "Wrecker (w)"),
            ):
                tk.Button(
                    buttons, text=label, command=lambda k=key: self.set_group(k)
                ).pack(side=tk.LEFT, padx=4, pady=4)
            tk.Button(buttons, text="Undo (u)", command=self.undo).pack(
                side=tk.LEFT, padx=4
            )
            tk.Button(buttons, text="Save & Quit (s)", command=self.save).pack(
                side=tk.LEFT, padx=4
            )
            self.canvas.bind("<Button-1>", self.add_point)
            self.canvas.bind("<Button-3>", lambda _e: self.undo())
        else:
            tk.Button(buttons, text="Save & Quit (s)", command=self.save).pack(
                side=tk.LEFT, padx=4, pady=4
            )
            tk.Button(buttons, text="Clear", command=self.clear_selection).pack(
                side=tk.LEFT, padx=4
            )
            self.canvas.bind("<Button-1>", self.drag_begin)
            self.canvas.bind("<B1-Motion>", self.drag_move)
            self.canvas.bind("<ButtonRelease-1>", self.drag_end)
        root.bind("<Key>", self.on_key)

        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.disp_image)
        self.redraw()

    # ---------- strategy ----------
    def set_group(self, key: str) -> None:
        self.active = key
        self.redraw()

    def add_point(self, event) -> None:
        self.groups[self.active].append(display_to_image(event.x, event.y, self.scale))
        self.redraw()

    def undo(self) -> None:
        if self.groups[self.active]:
            self.groups[self.active].pop()
        self.redraw()

    # ---------- template ----------
    def drag_begin(self, event) -> None:
        self.drag_start = (event.x, event.y)
        if self.rect_id:
            self.canvas.delete(self.rect_id)
        self.rect_id = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y, outline="#ffeb3b", width=2
        )

    def drag_move(self, event) -> None:
        if self.rect_id and self.drag_start:
            self.canvas.coords(
                self.rect_id, self.drag_start[0], self.drag_start[1], event.x, event.y
            )

    def drag_end(self, event) -> None:
        if not self.drag_start:
            return
        x1, y1 = display_to_image(*self.drag_start, self.scale)
        x2, y2 = display_to_image(event.x, event.y, self.scale)
        left, top = min(x1, x2), min(y1, y2)
        width, height = abs(x2 - x1), abs(y2 - y1)
        if width >= 4 and height >= 4:
            self.selection = (left, top, width, height)
        self.drag_start = None
        self.rect_id = None
        self.redraw()

    def clear_selection(self) -> None:
        self.selection = None
        self.redraw()

    # ---------- common ----------
    def on_key(self, event) -> None:
        key = event.keysym.lower()
        if key == "escape":
            self.root.destroy()
        elif key == "s":
            self.save()
        elif self.mode == "strategy" and key == "u":
            self.undo()
        elif self.mode == "strategy" and key in GROUP_KEYS:
            self.set_group(GROUP_KEYS[key])

    def redraw(self) -> None:
        self.canvas.delete("mark")
        if self.mode == "strategy":
            for group, points in self.groups.items():
                for index, (x, y) in enumerate(points, start=1):
                    dx, dy = int(x * self.scale), int(y * self.scale)
                    self.canvas.create_oval(
                        dx - 7,
                        dy - 7,
                        dx + 7,
                        dy + 7,
                        outline="#ffffff",
                        width=2,
                        fill=GROUP_COLORS[group],
                        tags="mark",
                    )
                    self.canvas.create_text(
                        dx + 14,
                        dy - 10,
                        text=f"{group[0].upper()}{index}",
                        fill="#ffffff",
                        font=("Consolas", 10, "bold"),
                        tags="mark",
                    )
            counts = "  ".join(f"{g}={len(p)}" for g, p in self.groups.items())
            self.status.config(
                text=(
                    f"grup aktif: {self.active} | {counts}\n"
                    "klik = tambah titik | klik-kanan/u = undo | d/b/w = ganti grup | s = simpan | Esc = batal"
                )
            )
        else:
            self.status.config(text="drag kotak pada gambar | s = simpan | Esc = batal")
            if self.selection:
                x, y, w, h = self.selection
                self.canvas.create_rectangle(
                    x * self.scale,
                    y * self.scale,
                    (x + w) * self.scale,
                    (y + h) * self.scale,
                    outline="#ffeb3b",
                    width=2,
                    tags="mark",
                )
                self.status.config(
                    text=f"pilihan: x={x} y={y} w={w} h={h} | s = simpan | Esc = batal"
                )

    def save(self) -> None:
        if self.mode == "strategy":
            size = (self.image.width, self.image.height)
            dragon = points_to_percent(self.groups["dragon"], size)
            balloon = points_to_percent(self.groups["balloon"], size)
            wrecker = points_to_percent(self.groups["wall_wrecker"][:1], size)
            if not dragon and not balloon and not wrecker:
                self.status.config(
                    text="kosong! tambahkan minimal 1 titik sebelum simpan"
                )
                return
            save_strategy(
                self.name, dragon, balloon, wrecker[0] if wrecker else None, self.out_path
            )
            print(f"saved strategy '{self.name}' to {self.out_path}")
        else:
            if not self.selection:
                self.status.config(text="belum ada seleksi — drag kotak dulu")
                return
            out = Path(self.assets_dir) / f"{self.name}.png"
            crop_and_save(self.image_path, self.selection, out)
            pct = region_percent(self.selection, (self.image.width, self.image.height))
            print(
                f"saved template {out} region=({pct[0]:.3f}, {pct[1]:.3f}, {pct[2]:.3f}, {pct[3]:.3f})"
            )
        self.root.destroy()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="picker")
    parser.add_argument("--image", required=True)
    parser.add_argument("--mode", choices=("strategy", "template"), default="strategy")
    parser.add_argument("--name", default="Scenario1")
    parser.add_argument("--out", default="AttackStrategies.json")
    parser.add_argument("--assets", default="assets")
    args = parser.parse_args(argv)

    root = tk.Tk()
    PickerApp(root, args.image, args.mode, args.name, args.out, args.assets)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
