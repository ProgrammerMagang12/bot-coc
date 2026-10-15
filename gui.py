"""GARUDA — GUI bot CoC: atur loot minimum, Start/Stop, multi-instance.

Jalankan:
    py gui.py

Setiap "profil" = satu file config penuh di folder profiles/ (bisa untuk
emulator/akun berbeda — multi-instance jalan paralel per profil).
"""

from __future__ import annotations

import json
import logging
import queue
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk

from coclab import profiles
from coclab.adb import Adb
from coclab.config import ConfigError, load_config
from coclab.loop import run
from coclab.paths import base_dir

ROOT = base_dir()
TEMPLATE = ROOT / "config.json" if (ROOT / "config.json").is_file() else ROOT / "config.example.json"
RUN_UNTIL = 999  # bot jalan sampai: kamu Stop / DE penuh / pasukan habis / gagal

# -- palet -----------------------------------------------------------------------
BG = "#13131f"
PANEL = "#1b1b2c"
CARD = "#23233a"
CARD_HOVER = "#282845"
SIDEBAR = "#181828"
FIELD_BG = "#0f0f1a"
FG = "#ececf7"
FG_DIM = "#8d8dae"
FG_FAINT = "#5c5c7a"
BORDER = "#2b2b45"
AMBER = "#ffb454"
AMBER_DARK = "#d99436"
GREEN = "#2ecc71"
GREEN_DARK = "#25a05a"
RED = "#e74c3c"
RED_DARK = "#b03a2e"
BLUE = "#3d9be9"
BLUE_DARK = "#2d78b5"

STATUS_COLORS = {
    "running": GREEN,
    "ok": "#5ef2c0",
    "stopped": AMBER,
    "failed": RED,
    "idle": FG_FAINT,
}

log_queue: "queue.Queue[tuple[str, str]]" = queue.Queue()

FORM_FIELDS = (
    ("device_address", "Alamat emulator (adb)"),
    ("min_gold", "Loot minimal: Gold"),
    ("min_elixir", "Loot minimal: Elixir"),
    ("min_dark", "Loot minimal: Dark Elixir"),
    ("de_full_value", "Auto-stop: DE penuh di angka"),
    ("speed_up_taps", "Percepat battle (2 = x4)"),
    ("end_delay_s", "Maks tunggu battle (detik)"),
    ("emulator_path", "File emulator (auto-buka)"),
)
ARMY_FIELDS = (
    ("dragon_drops", "Dragon"),
    ("balloon_drops", "Balloon"),
    ("wall_wrecker_drop", "Siege"),
    ("extra_troop", "Extra troop"),
    ("rage_spell", "Rage"),
    ("freeze_spell", "Freeze"),
)
FORM_HINT = (
    "Isi 0 pada 'Dark Elixir' / 'Auto-stop' untuk menonaktifkan. "
    "Bot jalan sampai kamu Stop / DE penuh / pasukan habis."
)


class _QueueLogHandler(logging.Handler):
    """Kirim log milik thread instance ini ke GUI lewat queue."""

    def __init__(self, name: str):
        super().__init__()
        self.instance_name = name
        tid = threading.get_ident()
        self.addFilter(lambda record: record.thread == tid)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
        except Exception:  # noqa: BLE001
            msg = record.getMessage()
        log_queue.put((self.instance_name, msg))


class _Instance:
    def __init__(self) -> None:
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()

    @property
    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()


def _status_kind(text: str) -> str:
    low = (text or "").lower()
    if low.startswith("jalan"):
        return "running"
    if low.startswith("ok"):
        return "ok"
    if low.startswith("dihentikan") or low.startswith("berhenti"):
        return "stopped"
    if low.startswith("gagal") or low.startswith("error") or low.startswith("emulator"):
        return "failed"
    return "idle"


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("GARUDA — CoC Raid Bot")
        root.geometry("840x560")
        root.minsize(780, 500)
        root.configure(bg=BG)
        self.instances: dict[str, _Instance] = {}
        self.form_vars: dict[str, tk.StringVar] = {}
        self.army_vars: dict[str, tk.StringVar] = {}
        self.status: dict[str, str] = {}
        self.selected: str | None = None
        self._build_ui()
        self._refresh_profiles()
        self.root.after(150, self._drain_logs)

    # -- widgets ------------------------------------------------------------------
    def _flat_button(self, parent, text, bg, bg_dark, command, font=None, width=None, pady=3):
        btn = tk.Button(
            parent,
            text=text,
            bg=bg,
            fg="white",
            activebackground=bg_dark,
            activeforeground="white",
            relief="flat",
            cursor="hand2",
            command=command,
            font=font or ("Segoe UI", 9, "bold"),
            bd=0,
            padx=9,
            pady=pady,
            **(dict(width=width) if width else {}),
        )
        btn.bind("<Enter>", lambda _e: btn.config(bg=bg_dark))
        btn.bind("<Leave>", lambda _e: btn.config(bg=bg))
        return btn

    def _dark_entry(self, parent, var, width=20, justify="left"):
        return tk.Entry(
            parent,
            textvariable=var,
            width=width,
            bg=FIELD_BG,
            fg=FG,
            insertbackground=AMBER,
            relief="flat",
            justify=justify,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=AMBER,
            font=("Segoe UI", 9),
        )

    def _danger(self, parent, var, width=6):
        return self._dark_entry(parent, var, width=width, justify="center")

    # -- UI -----------------------------------------------------------------
    def _build_ui(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
        style.configure(
            "TNotebook.Tab",
            background=PANEL,
            foreground=FG_DIM,
            padding=[13, 5],
            font=("Segoe UI", 9, "bold"),
            borderwidth=0,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", CARD)],
            foreground=[("selected", AMBER)],
        )

        header = tk.Frame(self.root, bg=PANEL, height=44)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="🦅 GARUDA", bg=PANEL, fg=AMBER, font=("Segoe UI", 14, "bold")).pack(
            side="left", padx=(12, 6)
        )
        tk.Label(header, text="CoC Raid Bot", bg=PANEL, fg=FG_DIM, font=("Segoe UI", 8)).pack(
            side="left", pady=(8, 0)
        )
        tk.Label(header, text="● siap", bg=PANEL, fg=FG_FAINT, font=("Segoe UI", 8)).pack(
            side="right", padx=12
        )

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=8, pady=6)

        # ---------------- sidebar (kompak) ----------------
        side = tk.Frame(body, bg=SIDEBAR, width=200, highlightthickness=1, highlightbackground=BORDER)
        side.pack(side="left", fill="y", padx=(0, 6))
        side.pack_propagate(False)
        tk.Label(side, text="AKUN", bg=SIDEBAR, fg=AMBER, font=("Segoe UI", 9, "bold")).pack(
            anchor="w", padx=10, pady=(8, 4)
        )
        listwrap = tk.Frame(side, bg=SIDEBAR)
        listwrap.pack(fill="both", expand=True, padx=(4, 1))
        self.acc_canvas = tk.Canvas(listwrap, bg=SIDEBAR, highlightthickness=0, width=182)
        acc_scroll = tk.Scrollbar(listwrap, orient="vertical", command=self.acc_canvas.yview, bd=0)
        self.acc_canvas.configure(yscrollcommand=acc_scroll.set)
        acc_scroll.pack(side="right", fill="y")
        self.acc_canvas.pack(side="left", fill="both", expand=True)
        self.acc_inner = tk.Frame(self.acc_canvas, bg=SIDEBAR)
        self._acc_window = self.acc_canvas.create_window((0, 0), window=self.acc_inner, anchor="nw")
        self.acc_inner.bind(
            "<Configure>",
            lambda _e: self.acc_canvas.configure(scrollregion=self.acc_canvas.bbox("all")),
        )
        self.acc_canvas.bind(
            "<Configure>",
            lambda e: self.acc_canvas.itemconfigure(self._acc_window, width=e.width),
        )
        btns = tk.Frame(side, bg=SIDEBAR)
        btns.pack(fill="x", padx=8, pady=8)
        self._flat_button(btns, "+ Tambah", BLUE, BLUE_DARK, self._add_profile).pack(
            side="left", expand=True, fill="x"
        )
        self._flat_button(btns, "✎", AMBER, AMBER_DARK, self._rename_profile, width=3).pack(
            side="left", padx=3
        )
        self._flat_button(btns, "✕", RED, RED_DARK, self._delete_profile, width=3).pack(
            side="left"
        )

        # ---------------- main: tabs + kontrol ----------------
        main = tk.Frame(body, bg=BG)
        main.pack(side="left", fill="both", expand=True)

        self.notebook = ttk.Notebook(main)
        self.notebook.pack(fill="both", expand=True)

        # tab 1: pengaturan
        tab_set = tk.Frame(self.notebook, bg=CARD)
        self.notebook.add(tab_set, text="⚙  Pengaturan")
        grid = tk.Frame(tab_set, bg=CARD)
        grid.pack(fill="both", expand=True, padx=12, pady=10)
        for i, (key, label) in enumerate(FORM_FIELDS):
            tk.Label(grid, text=label, bg=CARD, fg=FG_DIM, font=("Segoe UI", 8), anchor="w").grid(
                row=i, column=0, sticky="w", pady=2, padx=(0, 8)
            )
            var = tk.StringVar()
            self.form_vars[key] = var
            self._dark_entry(grid, var, width=30).grid(
                row=i, column=1, sticky="ew", pady=2, ipady=2
            )
        grid.columnconfigure(1, weight=1)
        tk.Label(
            grid, text=FORM_HINT, bg=CARD, fg=FG_FAINT, font=("Segoe UI", 7),
            wraplength=460, justify="left",
        ).grid(row=len(FORM_FIELDS), column=0, columnspan=2, sticky="w", pady=(8, 0))

        # tab 2: pasukan
        tab_army = tk.Frame(self.notebook, bg=CARD)
        self.notebook.add(tab_army, text="🛡  Pasukan")
        army = tk.Frame(tab_army, bg=CARD)
        army.pack(fill="both", expand=True, padx=12, pady=10)
        tk.Label(
            army, text="Jumlah tap per grup (jumlah pasukan di bar)", bg=CARD, fg=FG_DIM,
            font=("Segoe UI", 8),
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 6))
        for i, (key, label) in enumerate(ARMY_FIELDS):
            r, c = divmod(i, 2)
            tk.Label(army, text=label, bg=CARD, fg=FG_DIM, font=("Segoe UI", 8), anchor="w").grid(
                row=r + 1, column=c * 2, sticky="w", pady=3, padx=(0, 6)
            )
            var = tk.StringVar()
            self.army_vars[key] = var
            self._dark_entry(army, var, width=6, justify="center").grid(
                row=r + 1, column=c * 2 + 1, sticky="w", pady=3, padx=(0, 24), ipady=2
            )

        # tab 3: log
        tab_log = tk.Frame(self.notebook, bg=CARD)
        self.notebook.add(tab_log, text="📜  Log")
        logwrap = tk.Frame(tab_log, bg=CARD)
        logwrap.pack(fill="both", expand=True, padx=10, pady=(8, 10))
        top = tk.Frame(logwrap, bg=CARD)
        top.pack(fill="x")
        self._flat_button(
            top, "Bersihkan", "#3a3a58", "#2e2e45", self._clear_log, font=("Segoe UI", 8)
        ).pack(side="right")
        self._log_badge = tk.Label(
            top, text="—", bg=CARD, fg=FG_FAINT, font=("Segoe UI", 8, "bold")
        )
        self._log_badge.pack(side="left")
        scroll = tk.Scrollbar(logwrap, bg=CARD, troughcolor=PANEL, bd=0)
        scroll.pack(side="right", fill="y")
        self.log_text = tk.Text(
            logwrap, height=10, state="disabled", wrap="none",
            bg="#0b0b14", fg="#c9c9dd", relief="flat", highlightthickness=0,
            font=("Consolas", 9), yscrollcommand=scroll.set,
        )
        self.log_text.pack(fill="both", expand=True, pady=(4, 0))
        scroll.config(command=self.log_text.yview)
        self.log_text.tag_configure("err", foreground="#ff8a8a")
        self.log_text.tag_configure("ok", foreground="#7dffb8")
        self.log_text.tag_configure("warn", foreground="#ffd27d")
        self.log_text.tag_configure("head", foreground=AMBER)

        # ---------------- kontrol (selalu terlihat) ----------------
        ctrl = tk.Frame(main, bg=BG)
        ctrl.pack(fill="x", pady=(6, 0))
        self._flat_button(ctrl, "💾 Simpan", BLUE, BLUE_DARK, self._save_current).pack(side="left")
        self._flat_button(
            ctrl, "▶  START", GREEN, GREEN_DARK, self._start,
            font=("Segoe UI", 10, "bold"), width=10, pady=5,
        ).pack(side="left", padx=6)
        self._flat_button(
            ctrl, "■  STOP", RED, RED_DARK, self._stop,
            font=("Segoe UI", 10, "bold"), width=8, pady=5,
        ).pack(side="left")
        self.status_label = tk.Label(
            ctrl, text="—", bg=PANEL, fg=FG_DIM, font=("Segoe UI", 9, "bold"), padx=10, pady=3
        )
        self.status_label.pack(side="left", padx=12)

    # -- dialog gelap ---------------------------------------------------------
    def _dialog(self, title, prompt, buttons, entry=False, initial="") -> object:
        win = tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg=PANEL)
        win.transient(self.root)
        win.resizable(False, False)
        result: dict = {"value": None}
        tk.Label(win, text=title, bg=PANEL, fg=AMBER, font=("Segoe UI", 11, "bold")).pack(
            anchor="w", padx=16, pady=(14, 2)
        )
        tk.Label(
            win, text=prompt, bg=PANEL, fg=FG, font=("Segoe UI", 9), wraplength=340, justify="left"
        ).pack(anchor="w", padx=16)
        var = tk.StringVar(value=initial)
        entry_widget = None
        if entry:
            entry_widget = self._dark_entry(win, var, width=38)
            entry_widget.pack(fill="x", padx=16, pady=(10, 0), ipady=4)
        btns = tk.Frame(win, bg=PANEL)
        btns.pack(fill="x", padx=16, pady=14)

        def ok(_event=None):
            result["value"] = var.get() if entry else True
            win.destroy()

        def cancel(_event=None):
            result["value"] = None if entry else False
            win.destroy()

        self._flat_button(btns, buttons[0][0], buttons[0][1], buttons[0][2], ok).pack(side="right")
        self._flat_button(btns, buttons[1][0], "#3a3a58", "#2e2e45", cancel).pack(
            side="right", padx=(0, 8)
        )
        win.bind("<Return>", ok)
        win.bind("<Escape>", cancel)
        win.update_idletasks()
        w = max(win.winfo_reqwidth(), 300)
        h = win.winfo_reqheight()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - w) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - h) // 2
        win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        win.grab_set()
        if entry_widget is not None:
            entry_widget.focus_set()
            entry_widget.select_range(0, "end")
        self.root.wait_window(win)
        return result["value"]

    def _ask_string(self, title, prompt, initial=""):
        return self._dialog(
            title, prompt,
            [("OK", GREEN, GREEN_DARK), ("Batal", None, None)],
            entry=True, initial=initial,
        )

    def _ask_yes_no(self, title, message) -> bool:
        return self._dialog(
            title, message, [("Ya", GREEN, GREEN_DARK), ("Tidak", RED, RED_DARK)], entry=False
        ) is True

    def _info(self, title, message) -> None:
        self._dialog(title, message, [("OK", BLUE, BLUE_DARK), ("Tutup", None, None)], entry=False)

    def _error(self, title, message) -> None:
        self._dialog(title, message, [("OK", RED, RED_DARK), ("Tutup", None, None)], entry=False)

    # -- daftar akun ----------------------------------------------------------
    def _refresh_profiles(self, select: str | None = None) -> None:
        names = profiles.list_profiles()
        if select in names:
            self.selected = select
        if self.selected not in names:
            self.selected = names[0] if names else None
        for child in self.acc_inner.winfo_children():
            child.destroy()
        for name in names:
            self._account_card(name)
        if self.selected:
            self._on_select()

    def _account_card(self, name: str) -> None:
        selected = name == self.selected
        running = name in self.instances and self.instances[name].running
        kind = "running" if running else _status_kind(self.status.get(name, ""))
        dot = STATUS_COLORS.get(kind, FG_FAINT)
        card_bg = CARD if selected else SIDEBAR
        card = tk.Frame(
            self.acc_inner, bg=card_bg, cursor="hand2",
            highlightthickness=1, highlightbackground=(AMBER if selected else BORDER),
        )
        card.pack(fill="x", padx=3, pady=2)
        bar = tk.Frame(card, bg=(AMBER if selected else card_bg), width=3)
        bar.pack(side="left", fill="y")
        inner = tk.Frame(card, bg=card_bg)
        inner.pack(side="left", fill="x", expand=True, padx=7, pady=4)
        widgets = [card, bar, inner]
        row1 = tk.Frame(inner, bg=card_bg)
        row1.pack(fill="x")
        widgets.append(row1)
        widgets.append(tk.Label(row1, text="●", fg=dot, bg=card_bg, font=("Segoe UI", 8)))
        widgets[-1].pack(side="left")
        widgets.append(
            tk.Label(row1, text=name, fg=FG, bg=card_bg, font=("Segoe UI", 9, "bold"), anchor="w")
        )
        widgets[-1].pack(side="left", padx=(4, 0))
        status_text = self.status.get(name, "")
        if status_text:
            widgets.append(
                tk.Label(row1, text=status_text[:14], fg=dot, bg=card_bg, font=("Segoe UI", 7))
            )
            widgets[-1].pack(side="right")
        device = ""
        try:
            device = str(profiles.load_profile(name).get("device_address", ""))
        except Exception:  # noqa: BLE001
            pass
        widgets.append(
            tk.Label(inner, text=device, fg=FG_DIM, bg=card_bg, font=("Segoe UI", 7), anchor="w")
        )
        widgets[-1].pack(fill="x", padx=(12, 0))
        for widget in widgets:
            widget.bind("<Button-1>", lambda _e, n=name: self._select_account(n))
            widget.bind(
                "<Enter>",
                lambda _e, ws=widgets: [
                    w.config(bg=CARD_HOVER) for w in ws if w.cget("bg") in (SIDEBAR, CARD)
                ],
            )
            widget.bind(
                "<Leave>",
                lambda _e, ws=widgets: [
                    w.config(bg=(CARD if selected else SIDEBAR))
                    for w in ws
                    if w.cget("bg") == CARD_HOVER
                ],
            )

    def _select_account(self, name: str) -> None:
        self.selected = name
        self._refresh_profiles(select=name)

    def _on_select(self) -> None:
        name = self.selected
        if not name:
            return
        try:
            data = profiles.load_profile(name)
        except Exception as exc:  # noqa: BLE001
            self._error("Gagal memuat", str(exc))
            return
        for key, _label in FORM_FIELDS:
            self.form_vars[key].set(str(data.get(key, "")))
        army = data.get("army", {})
        for key, _label in ARMY_FIELDS:
            self.army_vars[key].set(str(army.get(key, "")))
        self._set_status_label(name)

    def _set_status_label(self, name: str | None) -> None:
        text = self.status.get(name or "", "—")
        kind = _status_kind(text)
        if text == "—":
            self.status_label.config(text=text, bg=PANEL, fg=FG_DIM)
        else:
            color = STATUS_COLORS.get(kind, FG_DIM)
            self.status_label.config(text=text, bg=color, fg="#10101c")
        if hasattr(self, "_log_badge"):
            self._log_badge.config(text=text, fg=STATUS_COLORS.get(kind, FG_FAINT))

    # -- aksi profil ----------------------------------------------------------
    def _add_profile(self) -> None:
        name = self._ask_string("Akun baru", "Nama akun / instance:")
        if not name:
            return
        name = "".join(ch for ch in name if ch.isalnum() or ch in "-_ ").strip()
        if not name:
            return
        try:
            profiles.create_from_template(name, TEMPLATE)
        except Exception as exc:  # noqa: BLE001
            self._error("Gagal", str(exc))
            return
        self._refresh_profiles(select=name)

    def _rename_profile(self) -> None:
        old = self.selected
        if not old:
            return
        if self.instances.get(old) and self.instances[old].running:
            self._info("Masih jalan", "Stop dulu instance ini sebelum ganti nama.")
            return
        new = self._ask_string("Ganti nama akun", f"Nama baru untuk '{old}':", initial=old)
        if not new or new == old:
            return
        new = "".join(ch for ch in new if ch.isalnum() or ch in "-_ ").strip()
        if not new:
            return
        try:
            profiles.rename_profile(old, new)
        except Exception as exc:  # noqa: BLE001
            self._error("Gagal ganti nama", str(exc))
            return
        inst = self.instances.pop(old, None)
        if inst is not None:
            self.instances[new] = inst
        if old in self.status:
            self.status[new] = self.status.pop(old)
        self._refresh_profiles(select=new)

    def _delete_profile(self) -> None:
        name = self.selected
        if not name:
            return
        if self.instances.get(name) and self.instances[name].running:
            self._info("Masih jalan", "Stop dulu instance ini.")
            return
        if not self._ask_yes_no("Hapus akun", f"Hapus profil '{name}'?"):
            return
        profiles.profile_path(name).unlink(missing_ok=True)
        self.instances.pop(name, None)
        self.status.pop(name, None)
        self.selected = None
        self._refresh_profiles()

    def _save_current(self) -> None:
        name = self.selected
        if not name:
            return
        try:
            data = profiles.load_profile(name)
            template = json.loads(TEMPLATE.read_text(encoding="utf-8"))
            if isinstance(template, dict):
                filled = profiles.merge_missing(data, template)
                if filled:
                    log_queue.put((name, f"Profil diperbarui otomatis: {filled} setting baru"))
            for key, _label in FORM_FIELDS:
                raw = self.form_vars[key].get().strip()
                if key in ("device_address", "emulator_path"):
                    data[key] = raw
                    continue
                if raw == "":
                    continue  # field kosong → biarkan nilai lama
                data[key] = int(raw)
            army = data.setdefault("army", {})
            for key, _label in ARMY_FIELDS:
                raw = self.army_vars[key].get().strip()
                if raw:
                    army[key] = int(raw)
            if "ldconsole" in str(data.get("emulator_path", "")).lower():
                index = profiles.ldplayer_index_for_address(data.get("device_address", ""))
                if index is not None:
                    data["emulator_args"] = ["launch", "--index", str(index)]
            profiles.save_profile(name, data)
            self.status_label.config(text="tersimpan ✓", bg=GREEN, fg="#10101c")
        except (ValueError, ConfigError) as exc:
            self._error("Input tidak valid", str(exc))
        except Exception as exc:  # noqa: BLE001
            self._error("Gagal menyimpan", str(exc))

    # -- start/stop -----------------------------------------------------------
    def _start(self) -> None:
        name = self.selected
        if not name:
            return
        self._save_current()
        inst = self.instances.setdefault(name, _Instance())
        if inst.running:
            self._info("Sudah jalan", f"Instance '{name}' sedang berjalan.")
            return
        inst.stop_event.clear()
        try:
            cfg = load_config(profiles.profile_path(name))  # validasi awal
        except Exception as exc:  # noqa: BLE001
            self._error("Config tidak valid", str(exc))
            return
        inst.thread = threading.Thread(
            target=self._run_instance, args=(name, cfg, inst), daemon=True
        )
        inst.thread.start()
        self.status[name] = f"jalan ({cfg.device_address})"
        self._refresh_profiles(select=name)

    def _device_online(self, cfg) -> bool:
        try:
            adb = Adb(cfg.adb_path)
            serial = adb.connect(cfg.device_address)
            adb.wm_size(serial)
            return True
        except Exception:  # noqa: BLE001
            return False

    def _ensure_emulator(self, name: str, cfg, inst: _Instance) -> bool:
        """Pastikan emulator + device online; jalankan emulator bila perlu."""
        if self._device_online(cfg):
            return True
        if not cfg.emulator_path:
            log_queue.put((name, "Device offline & File emulator kosong — isi di pengaturan."))
            return False
        cmd = [cfg.emulator_path, *cfg.emulator_args]
        if "ldconsole" in str(cfg.emulator_path).lower():
            index = profiles.ldplayer_index_for_address(cfg.device_address)
            if index is not None:
                cmd = [cfg.emulator_path, "launch", "--index", str(index)]
        log_queue.put((name, f"Emulator belum jalan — menjalankan: {' '.join(cmd)}"))
        try:
            subprocess.Popen(cmd)  # noqa: S603 - path dari config user sendiri
        except OSError as exc:
            log_queue.put((name, f"Gagal menjalankan emulator: {exc}"))
            return False
        adb = Adb(cfg.adb_path)
        deadline = time.time() + 180
        while time.time() < deadline:
            if inst.stop_event.is_set():
                return False
            try:
                serial = adb.connect(cfg.device_address)
                adb.wm_size(serial)
                log_queue.put((name, "Emulator online ✓"))
                return True
            except Exception:  # noqa: BLE001
                time.sleep(5)
        log_queue.put((name, "Timeout menunggu emulator online (180 s)"))
        return False

    def _run_instance(self, name: str, cfg, inst: _Instance) -> None:
        handler = _QueueLogHandler(name)
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        log_queue.put((name, f">>> START {name} @ {cfg.device_address} (sampai stop / DE penuh)"))
        try:
            if not self._ensure_emulator(name, cfg, inst):
                log_queue.put((name, "<<< FAILED: emulator tidak siap"))
                self.status[name] = "emulator tidak siap"
                return
            summary = run(cfg, "live", RUN_UNTIL, should_stop=inst.stop_event.is_set)
            if summary.ok:
                extra = f" ({summary.reason})" if summary.reason else ""
                line = f"<<< OK: {summary.cycles_done} cycle selesai{extra}"
            else:
                line = f"<<< FAILED: {summary.reason}"
            log_queue.put((name, line))
            if summary.ok:
                self.status[name] = "OK ✓"
            elif summary.reason == "stopped by user":
                self.status[name] = "dihentikan ■"
            else:
                self.status[name] = f"gagal: {summary.reason}"
        except Exception as exc:  # noqa: BLE001
            log_queue.put((name, f"<<< ERROR: {exc}"))
            self.status[name] = "error"
        finally:
            root_logger.removeHandler(handler)
            log_queue.put((name, "__DONE__"))

    def _stop(self) -> None:
        name = self.selected
        if not name:
            return
        inst = self.instances.get(name)
        if inst and inst.running:
            inst.stop_event.set()
            self.status[name] = "berhenti diminta…"
            self._set_status_label(name)

    # -- log ------------------------------------------------------------------
    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _drain_logs(self) -> None:
        try:
            while True:
                name, msg = log_queue.get_nowait()
                if msg == "__DONE__":
                    self._refresh_profiles()
                    self._set_status_label(self.selected)
                    continue
                upper = msg.upper()
                tag = ()
                if "FAILED" in upper or "ERROR" in upper or "GAGAL" in upper:
                    tag = ("err",)
                elif "OK:" in upper or "✓" in msg:
                    tag = ("ok",)
                elif "WARNING" in upper:
                    tag = ("warn",)
                self.log_text.configure(state="normal")
                self.log_text.insert("end", f"[{name}] ", ("head",))
                self.log_text.insert("end", f"{msg}\n", tag)
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(150, self._drain_logs)

    def on_close(self) -> None:
        for inst in self.instances.values():
            inst.stop_event.set()
        self.root.destroy()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    root = tk.Tk()
    app = App(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
