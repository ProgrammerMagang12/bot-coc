"""CROWZ LAB — GUI bot CoC (seperti CROWZ): atur loot minimum, Start/Stop, multi-instance.

Jalankan:
    py gui.py

Setiap "profil" = satu file config penuh di folder profiles/ (bisa untuk
emulator/akun berbeda — multi-instance jalan paralel per profil).
"""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from coclab import profiles
from coclab.config import ConfigError, load_config
from coclab.loop import run

ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "config.json" if (ROOT / "config.json").is_file() else ROOT / "config.example.json"

log_queue: "queue.Queue[tuple[str, str]]" = queue.Queue()

FORM_FIELDS = (
    ("device_address", "Device (adb)"),
    ("min_gold", "Min Gold"),
    ("min_elixir", "Min Elixir"),
    ("min_dark", "Min Dark (0 = abaikan)"),
    ("speed_up_taps", "Speed-up taps (2 = x4)"),
    ("end_delay_s", "Max tunggu battle (s)"),
    ("threshold", "Template threshold"),
    ("cycles", "Cycles"),
)
ARMY_FIELDS = (
    ("dragon_drops", "Dragon"),
    ("balloon_drops", "Balloon"),
    ("wall_wrecker_drop", "Siege"),
    ("extra_troop", "Extra troop"),
    ("rage_spell", "Rage"),
    ("freeze_spell", "Freeze"),
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
        self.cycles = 1

    @property
    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("CROWZ LAB — CoC Bot")
        root.geometry("860x620")
        self.instances: dict[str, _Instance] = {}
        self.form_vars: dict[str, tk.StringVar] = {}
        self.army_vars: dict[str, tk.StringVar] = {}
        self.status: dict[str, str] = {}
        self._build_ui()
        self._refresh_profiles()
        self.root.after(150, self._drain_logs)

    # -- UI -----------------------------------------------------------------
    def _build_ui(self) -> None:
        left = ttk.Frame(self.root, padding=8)
        left.pack(side="left", fill="y")
        ttk.Label(left, text="Akun / Instance").pack(anchor="w")
        self.listbox = tk.Listbox(left, width=22, exportselection=False)
        self.listbox.pack(fill="y", expand=True)
        self.listbox.bind("<<ListboxSelect>>", lambda _e: self._on_select())
        btns = ttk.Frame(left)
        btns.pack(fill="x", pady=4)
        ttk.Button(btns, text="Tambah", command=self._add_profile).pack(side="left", expand=True)
        ttk.Button(btns, text="Hapus", command=self._delete_profile).pack(side="left", expand=True)

        right = ttk.Frame(self.root, padding=8)
        right.pack(side="left", fill="both", expand=True)

        form = ttk.LabelFrame(right, text="Pengaturan", padding=8)
        form.pack(fill="x")
        for i, (key, label) in enumerate(FORM_FIELDS):
            r, c = divmod(i, 2)
            ttk.Label(form, text=label).grid(row=r, column=c * 2, sticky="w", padx=4, pady=2)
            var = tk.StringVar()
            self.form_vars[key] = var
            ttk.Entry(form, textvariable=var, width=18).grid(row=r, column=c * 2 + 1, sticky="w", padx=4)

        army = ttk.LabelFrame(right, text="Jumlah pasukan (tap per grup)", padding=8)
        army.pack(fill="x", pady=6)
        for i, (key, label) in enumerate(ARMY_FIELDS):
            r, c = divmod(i, 3)
            ttk.Label(army, text=label).grid(row=r, column=c * 2, sticky="w", padx=4, pady=2)
            var = tk.StringVar()
            self.army_vars[key] = var
            ttk.Entry(army, textvariable=var, width=8).grid(row=r, column=c * 2 + 1, sticky="w", padx=4)

        ctrl = ttk.Frame(right)
        ctrl.pack(fill="x", pady=4)
        ttk.Button(ctrl, text="Simpan", command=self._save_current).pack(side="left")
        self.start_btn = ttk.Button(ctrl, text="▶ Start", command=self._start)
        self.start_btn.pack(side="left", padx=6)
        self.stop_btn = ttk.Button(ctrl, text="■ Stop", command=self._stop)
        self.stop_btn.pack(side="left")
        self.status_var = tk.StringVar(value="—")
        ttk.Label(ctrl, textvariable=self.status_var).pack(side="left", padx=12)

        logframe = ttk.LabelFrame(right, text="Log", padding=4)
        logframe.pack(fill="both", expand=True)
        self.log_text = tk.Text(logframe, height=14, state="disabled", wrap="none")
        self.log_text.pack(fill="both", expand=True)

    # -- profil -------------------------------------------------------------
    def _refresh_profiles(self) -> None:
        self.listbox.delete(0, "end")
        for name in profiles.list_profiles():
            suffix = "  ●" if name in self.instances and self.instances[name].running else ""
            self.listbox.insert("end", f"{name}{suffix}")
        if self.listbox.size() and self.listbox.curselection() == ():
            self.listbox.selection_set(0)
            self._on_select()

    def _selected_name(self) -> str | None:
        sel = self.listbox.curselection()
        if not sel:
            return None
        return self.listbox.get(sel[0]).replace("  ●", "")

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
            if key == "cycles":
                inst = self.instances.get(name)
                self.form_vars["cycles"].set(str(inst.cycles if inst else 1))
                continue
            self.form_vars[key].set(str(data.get(key, "")))
        army = data.get("army", {})
        for key, _label in ARMY_FIELDS:
            self.army_vars[key].set(str(army.get(key, "")))
        self.status_var.set(self.status.get(name, "—"))

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
        self._refresh_profiles()

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
        self._refresh_profiles()

    def _save_current(self) -> None:
        name = self._selected_name()
        if not name:
            return
        try:
            data = profiles.load_profile(name)
            for key, _label in FORM_FIELDS:
                if key == "cycles":
                    inst = self.instances.setdefault(name, _Instance())
                    inst.cycles = max(1, int(self.form_vars["cycles"].get() or 1))
                    continue
                raw = self.form_vars[key].get().strip()
                if key == "device_address":
                    data[key] = raw
                elif key == "threshold":
                    data[key] = float(raw)
                else:
                    data[key] = int(raw)
            army = data.setdefault("army", {})
            for key, _label in ARMY_FIELDS:
                raw = self.army_vars[key].get().strip()
                if raw:
                    army[key] = int(raw)
            profiles.save_profile(name, data)
            self.status_var.set("tersimpan ✓")
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
        inst.thread = threading.Thread(target=self._run_instance, args=(name, cfg, inst), daemon=True)
        inst.thread.start()
        self.status[name] = f"jalan ({cfg.device_address})"
        self._refresh_profiles()
        self.status_var.set(self.status[name])

    def _run_instance(self, name: str, cfg, inst: _Instance) -> None:
        handler = _QueueLogHandler(name)
        handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%H:%M:%S"))
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        log_queue.put((name, f">>> START {name} @ {cfg.device_address} ({inst.cycles} cycle)"))
        try:
            summary = run(
                cfg,
                "live",
                inst.cycles,
                should_stop=inst.stop_event.is_set,
            )
            if summary.ok:
                line = f"<<< OK: {summary.cycles_done} cycle selesai"
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
            self.status_var.set(self.status[name])

    # -- log pump -----------------------------------------------------------
    def _drain_logs(self) -> None:
        try:
            while True:
                name, msg = log_queue.get_nowait()
                if msg == "__DONE__":
                    self._refresh_profiles()
                    if name == self._selected_name():
                        self.status_var.set(self.status.get(name, "—"))
                    continue
                self.log_text.configure(state="normal")
                self.log_text.insert("end", f"[{name}] {msg}\n")
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
