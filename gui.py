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
from pathlib import Path
from tkinter import messagebox, simpledialog

from coclab import profiles
from coclab.adb import Adb
from coclab.config import ConfigError, load_config
from coclab.loop import run

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "config.json" if (ROOT / "config.json").is_file() else ROOT / "config.example.json"
RUN_UNTIL = 999  # bot jalan sampai: kamu Stop / DE penuh / pasukan habis / gagal

# -- palet warna -----------------------------------------------------------------
BG = "#14141f"
PANEL = "#1d1d30"
PANEL_2 = "#171726"
SIDEBAR = "#181828"
FIELD_BG = "#101019"
FG = "#e8e8f5"
FG_DIM = "#8f8fb0"
AMBER = "#ffb454"
GREEN = "#2ecc71"
GREEN_DARK = "#1f9e55"
RED = "#e74c3c"
RED_DARK = "#b03a2e"
BLUE = "#3498db"
BLUE_DARK = "#2874a6"

STATUS_COLORS = {
    "running": GREEN,
    "ok": "#5ef2c0",
    "stopped": AMBER,
    "failed": RED,
    "idle": FG_DIM,
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
    "Isi 0 pada 'Loot minimal: Dark Elixir' atau 'Auto-stop' untuk menonaktifkan. "
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
        root.geometry("1000x660")
        root.configure(bg=BG)
        self.instances: dict[str, _Instance] = {}
        self.form_vars: dict[str, tk.StringVar] = {}
        self.army_vars: dict[str, tk.StringVar] = {}
        self.status: dict[str, str] = {}
        self._build_ui()
        self._refresh_profiles()
        self.root.after(150, self._drain_logs)

    # -- UI -----------------------------------------------------------------
    def _flat_button(self, parent, text, bg, bg_dark, command, font=None, width=None):
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
            padx=10,
            pady=4,
            **(dict(width=width) if width else {}),
        )
        return btn

    def _build_ui(self) -> None:
        # header
        header = tk.Frame(self.root, bg=PANEL, height=54)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header, text="🦅  GARUDA", bg=PANEL, fg=AMBER, font=("Segoe UI", 16, "bold")
        ).pack(side="left", padx=14)
        tk.Label(
            header,
            text="CoC Raid Bot — multi akun",
            bg=PANEL,
            fg=FG_DIM,
            font=("Segoe UI", 9),
        ).pack(side="left", pady=(9, 0))

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=10, pady=8)

        # sidebar
        side = tk.Frame(body, bg=SIDEBAR, width=190)
        side.pack(side="left", fill="y", padx=(0, 8))
        side.pack_propagate(False)
        tk.Label(side, text="AKUN", bg=SIDEBAR, fg=AMBER, font=("Segoe UI", 10, "bold")).pack(
            anchor="w", padx=10, pady=(8, 4)
        )
        self.listbox = tk.Listbox(
            side,
            bg=PANEL_2,
            fg=FG,
            selectbackground=AMBER,
            selectforeground="#1a1a2a",
            relief="flat",
            highlightthickness=0,
            font=("Segoe UI", 10),
            activestyle="none",
        )
        self.listbox.pack(fill="both", expand=True, padx=8)
        self.listbox.bind("<<ListboxSelect>>", lambda _e: self._on_select())
        btns = tk.Frame(side, bg=SIDEBAR)
        btns.pack(fill="x", padx=8, pady=8)
        self._flat_button(btns, "+ Tambah", BLUE, BLUE_DARK, self._add_profile).pack(
            fill="x", pady=2
        )
        self._flat_button(btns, "✎ Ganti Nama", "#c98a2e", "#a06f22", self._rename_profile).pack(
            fill="x", pady=2
        )
        self._flat_button(btns, "✕ Hapus", RED, RED_DARK, self._delete_profile).pack(
            fill="x", pady=2
        )

        # main area
        main = tk.Frame(body, bg=BG)
        main.pack(side="left", fill="both", expand=True)

        form_panel = tk.Frame(main, bg=PANEL)
        form_panel.pack(fill="x", pady=(0, 6))
        tk.Label(
            form_panel, text="⚙  PENGATURAN", bg=PANEL, fg=AMBER, font=("Segoe UI", 10, "bold")
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=10, pady=(6, 2))
        for i, (key, label) in enumerate(FORM_FIELDS):
            r, c = divmod(i, 2)
            tk.Label(form_panel, text=label, bg=PANEL, fg=FG, font=("Segoe UI", 9)).grid(
                row=r + 1, column=c * 2, sticky="w", padx=(10, 4), pady=2
            )
            var = tk.StringVar()
            self.form_vars[key] = var
            tk.Entry(
                form_panel,
                textvariable=var,
                width=20,
                bg=FIELD_BG,
                fg=FG,
                insertbackground=AMBER,
                relief="flat",
                highlightthickness=1,
                highlightbackground="#31314d",
                highlightcolor=AMBER,
            ).grid(row=r + 1, column=c * 2 + 1, sticky="w", padx=(0, 14), pady=2, ipady=3)
        hint_row = (len(FORM_FIELDS) + 1) // 2 + 1
        tk.Label(
            form_panel,
            text=FORM_HINT,
            bg=PANEL,
            fg=FG_DIM,
            font=("Segoe UI", 8),
            wraplength=640,
            justify="left",
        ).grid(row=hint_row, column=0, columnspan=4, sticky="w", padx=10, pady=(4, 8))

        army_panel = tk.Frame(main, bg=PANEL)
        army_panel.pack(fill="x", pady=(0, 6))
        tk.Label(
            army_panel,
            text="🛡  JUMLAH PASUKAN (tap per grup)",
            bg=PANEL,
            fg=AMBER,
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, columnspan=6, sticky="w", padx=10, pady=(6, 2))
        for i, (key, label) in enumerate(ARMY_FIELDS):
            r, c = divmod(i, 3)
            tk.Label(army_panel, text=label, bg=PANEL, fg=FG, font=("Segoe UI", 9)).grid(
                row=r + 1, column=c * 2, sticky="w", padx=(10, 4), pady=3
            )
            var = tk.StringVar()
            self.army_vars[key] = var
            tk.Entry(
                army_panel,
                textvariable=var,
                width=6,
                bg=FIELD_BG,
                fg=FG,
                insertbackground=AMBER,
                relief="flat",
                highlightthickness=1,
                highlightbackground="#31314d",
                highlightcolor=AMBER,
                justify="center",
            ).grid(row=r + 1, column=c * 2 + 1, sticky="w", padx=(0, 18), pady=3, ipady=3)

        ctrl = tk.Frame(main, bg=BG)
        ctrl.pack(fill="x", pady=(0, 6))
        self._flat_button(ctrl, "💾 Simpan", BLUE, BLUE_DARK, self._save_current).pack(side="left")
        self._flat_button(
            ctrl,
            "▶  START",
            GREEN,
            GREEN_DARK,
            self._start,
            font=("Segoe UI", 11, "bold"),
            width=12,
        ).pack(side="left", padx=8)
        self._flat_button(
            ctrl, "■  STOP", RED, RED_DARK, self._stop, font=("Segoe UI", 11, "bold"), width=10
        ).pack(side="left")
        self.status_var = tk.StringVar(value="—")
        self.status_label = tk.Label(
            ctrl, textvariable=self.status_var, bg=BG, fg=FG_DIM, font=("Segoe UI", 10, "bold")
        )
        self.status_label.pack(side="left", padx=14)

        log_panel = tk.Frame(main, bg=PANEL)
        log_panel.pack(fill="both", expand=True)
        tk.Label(
            log_panel, text="📜  LOG", bg=PANEL, fg=AMBER, font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", padx=10, pady=(6, 0))
        log_wrap = tk.Frame(log_panel, bg=PANEL)
        log_wrap.pack(fill="both", expand=True, padx=8, pady=6)
        scroll = tk.Scrollbar(log_wrap, bg=PANEL, troughcolor=PANEL_2, bd=0)
        scroll.pack(side="right", fill="y")
        self.log_text = tk.Text(
            log_wrap,
            height=12,
            state="disabled",
            wrap="none",
            bg="#0c0c16",
            fg="#c9c9dd",
            relief="flat",
            highlightthickness=0,
            font=("Consolas", 9),
            yscrollcommand=scroll.set,
        )
        self.log_text.pack(fill="both", expand=True)
        scroll.config(command=self.log_text.yview)
        self.log_text.tag_configure("err", foreground="#ff8a8a")
        self.log_text.tag_configure("ok", foreground="#7dffb8")
        self.log_text.tag_configure("warn", foreground="#ffd27d")

    # -- profil -------------------------------------------------------------
    def _set_status_label(self, name: str | None) -> None:
        text = self.status.get(name or "", "—")
        self.status_var.set(text)
        self.status_label.config(fg=STATUS_COLORS.get(_status_kind(text), FG_DIM))

    def _refresh_profiles(self, select: str | None = None) -> None:
        self.listbox.delete(0, "end")
        names = profiles.list_profiles()
        for name in names:
            marker = "● " if name in self.instances and self.instances[name].running else ""
            self.listbox.insert("end", f"{marker}{name}")
            idx = self.listbox.size() - 1
            kind = _status_kind(self.status.get(name, ""))
            color = STATUS_COLORS["running"] if marker else STATUS_COLORS.get(kind, FG)
            self.listbox.itemconfig(idx, fg=color)
        if names and self.listbox.curselection() == ():
            target = select if select in names else names[0]
            self.listbox.selection_set(names.index(target))
            self._on_select()
        elif select in names:
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(names.index(select))
            self._on_select()

    def _selected_name(self) -> str | None:
        sel = self.listbox.curselection()
        if not sel:
            return None
        return self.listbox.get(sel[0]).lstrip("● ")

    def _on_select(self) -> None:
        name = self._selected_name()
        if not name:
            return
        try:
            data = profiles.load_profile(name)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Gagal memuat", str(exc))
            return
        for key, _label in FORM_FIELDS:
            self.form_vars[key].set(str(data.get(key, "")))
        army = data.get("army", {})
        for key, _label in ARMY_FIELDS:
            self.army_vars[key].set(str(army.get(key, "")))
        self._set_status_label(name)

    def _add_profile(self) -> None:
        name = simpledialog.askstring("Profil baru", "Nama akun/instance:", parent=self.root)
        if not name:
            return
        name = "".join(ch for ch in name if ch.isalnum() or ch in "-_ ").strip()
        if not name:
            return
        try:
            profiles.create_from_template(name, TEMPLATE)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Gagal", str(exc))
            return
        self._refresh_profiles(select=name)

    def _rename_profile(self) -> None:
        old = self._selected_name()
        if not old:
            return
        if self.instances.get(old) and self.instances[old].running:
            messagebox.showinfo("Masih jalan", "Stop dulu instance ini sebelum ganti nama.")
            return
        new = simpledialog.askstring(
            "Ganti nama akun", f"Nama baru untuk '{old}':", parent=self.root, initialvalue=old
        )
        if not new or new == old:
            return
        new = "".join(ch for ch in new if ch.isalnum() or ch in "-_ ").strip()
        if not new:
            return
        try:
            profiles.rename_profile(old, new)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Gagal ganti nama", str(exc))
            return
        inst = self.instances.pop(old, None)
        if inst is not None:
            self.instances[new] = inst
        if old in self.status:
            self.status[new] = self.status.pop(old)
        self._refresh_profiles(select=new)

    def _delete_profile(self) -> None:
        name = self._selected_name()
        if not name:
            return
        if self.instances.get(name) and self.instances[name].running:
            messagebox.showinfo("Masih jalan", "Stop dulu instance ini.")
            return
        if not messagebox.askyesno("Hapus", f"Hapus profil '{name}'?"):
            return
        profiles.profile_path(name).unlink(missing_ok=True)
        self.instances.pop(name, None)
        self.status.pop(name, None)
        self._refresh_profiles()

    def _save_current(self) -> None:
        name = self._selected_name()
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
            profiles.save_profile(name, data)
            self.status_var.set("tersimpan ✓")
            self.status_label.config(fg=GREEN)
        except (ValueError, ConfigError) as exc:
            messagebox.showerror("Input tidak valid", str(exc))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Gagal menyimpan", str(exc))

    # -- start/stop ---------------------------------------------------------
    def _start(self) -> None:
        name = self._selected_name()
        if not name:
            return
        self._save_current()
        inst = self.instances.setdefault(name, _Instance())
        if inst.running:
            messagebox.showinfo("Sudah jalan", f"Instance '{name}' sedang berjalan.")
            return
        inst.stop_event.clear()
        try:
            cfg = load_config(profiles.profile_path(name))  # validasi awal
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Config tidak valid", str(exc))
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
        name = self._selected_name()
        if not name:
            return
        inst = self.instances.get(name)
        if inst and inst.running:
            inst.stop_event.set()
            self.status[name] = "berhenti diminta…"
            self._set_status_label(name)

    # -- log pump -----------------------------------------------------------
    def _drain_logs(self) -> None:
        try:
            while True:
                name, msg = log_queue.get_nowait()
                if msg == "__DONE__":
                    self._refresh_profiles()
                    self._set_status_label(self._selected_name())
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
                self.log_text.insert("end", f"[{name}] {msg}\n", tag)
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
