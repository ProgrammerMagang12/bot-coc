"""Bot orchestration: the v1 state machine with injected dependencies."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from coclab import cards, digits, vision, wallupgrade
from coclab.actions import Actions
from coclab.adb import Adb, AdbError
from coclab.capture import capture as capture_default
from coclab.config import Config
from coclab.state import BotState, StepResult
from coclab.strategy import (
    jitter_point,
    load_strategies as load_strategies_default,
    mirror_strategy,
)

logger = logging.getLogger(__name__)


def _never_stop() -> bool:
    return False


_MAX_LOOT_ROUNDS = 25


@dataclass
class RunSummary:
    ok: bool
    cycles_done: int
    reason: str = ""


@dataclass
class Deps:
    adb: object
    capture_fn: Callable[..., bool]
    load_image: Callable[..., object]
    find_template: Callable[..., vision.Match]
    crop_percent: Callable[..., object]
    ocr_digits: Callable[..., int | None]
    read_loot: Callable[..., int | None]
    read_de: Callable[..., int | None]
    read_badge: Callable[..., int | None]
    should_stop: Callable[..., bool]
    ocr_boxes: Callable[..., list]
    actions_factory: Callable[..., object]
    load_strategies: Callable[[str], list]
    sleep: Callable[[float], None]
    monotonic: Callable[[], float]
    state_hook: Callable[[str], None]


def _default_deps(config: Config) -> Deps:
    def find_template(img, tpl_path, threshold):
        return vision.find_template(img, vision.load_image(tpl_path), threshold)

    return Deps(
        adb=Adb(config.adb_path),
        capture_fn=capture_default,
        load_image=vision.load_image,
        find_template=find_template,
        crop_percent=vision.crop_percent,
        ocr_digits=vision.ocr_digits,
        read_loot=digits.read_loot_number,
        read_de=digits.read_home_number,
        read_badge=digits.read_badge_number,
        should_stop=_never_stop,
        ocr_boxes=vision.ocr_text_boxes,
        actions_factory=Actions,
        load_strategies=load_strategies_default,
        sleep=time.sleep,
        monotonic=time.monotonic,
        state_hook=lambda name: logger.info("STATE %s", name),
    )


def _safe_dir_name(device: str) -> str:
    return device.replace(".", "_").replace(":", "_")


class _Session:
    def __init__(self, config: Config, mode: str, deps: Deps) -> None:
        self.cfg = config
        self.mode = mode
        self.deps = deps
        self.assets = Path(config.assets_dir)
        self.device: str = ""
        self.actions = None
        self.workdir: Path = Path(config.workdir)
        self._deck_cards: dict[str, tuple[int, int, float]] = {}
        self._size: tuple[int, int] = (0, 0)

    # -- helpers ---------------------------------------------------------

    def _state(self, state: BotState) -> None:
        self.deps.state_hook(state.name)

    def _capture(self, name: str) -> Path | None:
        dest = self.workdir / name
        if self.deps.capture_fn(self.deps.adb, self.device, dest):
            return dest
        return None

    def _img(self, shot: Path):
        return self.deps.load_image(shot)

    def _match(self, shot: Path, template: str) -> vision.Match:
        return self.deps.find_template(
            self._img(shot), self.assets / template, self.cfg.threshold
        )

    def _match_safe(self, shot: Path, template: str) -> vision.Match:
        """Like _match but treats an unavailable template file as not-found."""
        if not (self.assets / template).is_file():
            return vision.Match(False, 0, 0, 0.0)
        try:
            return self._match(shot, template)
        except ValueError as exc:
            logger.info("Template %s unreadable (%s); skipped", template, exc)
            return vision.Match(False, 0, 0, 0.0)

    def _handle_afk_reload(self, shot: Path) -> bool:
        """'Anyone there? RELOAD GAME' popup: tap RELOAD and wait for the game to return."""
        try:
            boxes = self.deps.ocr_boxes(self._img(shot))
        except Exception as exc:  # noqa: BLE001 - OCR must never crash the loop
            logger.info("Disconnect OCR failed: %s", exc)
            return False
        reload_hit: tuple[int, int] | None = None
        popup_seen = False
        for text, cx, cy in boxes:
            upper = str(text).upper()
            if "RELOAD" in upper:
                reload_hit = (cx, cy)
                break
            if "DISCONNECTED" in upper or "ANYONE" in upper:
                popup_seen = True
        if reload_hit is not None:
            self.actions.tap_px(*reload_hit)
            logger.warning("Inactivity popup: tap RELOAD GAME, waiting for reload")
            self.deps.sleep(25)
            return True
        if popup_seen:
            for xp, yp in self.cfg.reload_game_cluster:
                self.actions.tap_percent(xp, yp)
            logger.warning("Inactivity popup: tap reload (cluster), waiting for reload")
            self.deps.sleep(25)
            return True
        return False

    def _handle_popups(self, shot: Path) -> bool:
        """Tangani popup lintas layar: AFK reload, Another_device, Client_error, Connection_lost."""
        if self._handle_afk_reload(shot):
            return True
        if self._popup_match(shot, "simplicity/ui/Another_device.png"):
            logger.warning(
                "Another device: akun aktif di perangkat lain - menunggu %ds (tanpa tap)",
                self.cfg.another_device_wait_s,
            )
            waited = 0
            while waited < self.cfg.another_device_wait_s and not self.deps.should_stop():
                step = min(1.0, self.cfg.another_device_wait_s - waited)
                self.deps.sleep(step)
                waited += step
            return True
        if self._popup_match(shot, "simplicity/ui/Client_error!.png"):
            logger.warning("Client_error terdeteksi - restart CoC")
            try:
                self.deps.adb.shell(self.device, f"am force-stop {self.cfg.coc_package}")
            except Exception as exc:  # noqa: BLE001
                logger.info("force-stop gagal: %s", exc)
            self._launch_coc()
            return True
        if self._popup_match(shot, "simplicity/ui/Connection_lost.png"):
            point = self.cfg.connection_lost_point or [0.5, 0.5]
            self.actions.tap_percent(*point)
            logger.warning("Connection lost - tap reconnect di %s", point)
            self.deps.sleep(10)
            return True
        return False

    def _popup_match(self, shot: Path, template: str) -> bool:
        try:
            return self._match_safe(shot, template).found
        except ValueError:
            return False

    def _coc_running(self) -> bool:
        """True bila aplikasi CoC terlihat di daftar proses device."""
        try:
            out = self.deps.adb.shell(self.device, "ps -A")
        except Exception as exc:  # noqa: BLE001
            logger.info("ps gagal (%s); anggap CoC jalan", exc)
            return True
        return self.cfg.coc_package in out

    def _resolve_coc_component(self) -> str | None:
        """Cari komponen launcher CoC via `cmd package resolve-activity`."""
        try:
            out = self.deps.adb.shell(
                self.device,
                "cmd package resolve-activity --brief -c android.intent.category.LAUNCHER "
                + self.cfg.coc_package,
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("resolve-activity gagal (%s)", exc)
            return None
        for line in reversed((out or "").splitlines()):
            line = line.strip()
            if line.startswith(self.cfg.coc_package) and "/" in line:
                return line
        return None

    def _ensure_coc(self) -> bool:
        """False bila CoC ternyata mati/crash (sudah dicoba dibuka ulang)."""
        if self._coc_running():
            return True
        logger.warning("CoC terdeteksi tertutup/crash - membuka ulang aplikasi")
        self._launch_coc()
        return False

    def _launch_coc(self) -> None:
        """CoC close/DC: buka aplikasinya lalu tunggu loading."""
        logger.warning("CoC tidak jalan — membuka aplikasi CoC...")
        opened = False
        component = self._resolve_coc_component()
        if component is None:
            component = f"{self.cfg.coc_package}/com.supercell.titan.GameApp"
        try:
            out = self.deps.adb.shell(self.device, f"am start -n {component}")
            opened = "starting" in (out or "").lower()
            if opened:
                logger.info("CoC dibuka via am start (%s)", component)
        except Exception as exc:  # noqa: BLE001
            logger.warning("am start gagal: %s", exc)
        if not opened:
            try:
                self.deps.adb.shell(
                    self.device,
                    f"monkey -p {self.cfg.coc_package} -c android.intent.category.LAUNCHER 1",
                )
                logger.info("CoC dibuka via monkey")
            except Exception as exc:  # noqa: BLE001
                logger.warning("monkey gagal juga: %s", exc)
        self.deps.sleep(30)

    def _home_de(self) -> int | None:
        shot = self._capture("home_de.png")
        if shot is None:
            return None
        crop = self.deps.crop_percent(self._img(shot), *self.cfg.de_roi)
        return self.deps.read_de(crop)

    def _collect_resources(self) -> None:
        """Ketuk titik kolektor (mine/pump/drill) yang sudah dikalibrasi — tap = collect."""
        if not self.cfg.collect_points:
            return
        logger.info("Collect resource (%d titik)", len(self.cfg.collect_points))
        for xp, yp in self.cfg.collect_points:
            if self.deps.should_stop():
                return
            self.actions.tap_percent(xp, yp)
            self.deps.sleep(self.cfg.tap_delay_ms / 1000)

    def _de_full(self) -> bool:
        """Stop condition: dark elixir storage at capacity → stop + close CoC."""
        if self.cfg.de_full_value <= 0:
            return False
        value = self._home_de()
        if value is None:
            logger.info("Home DE unreadable; continue")
            return False
        logger.info("Home DE: %s (stop di %s)", value, self.cfg.de_full_value)
        if value >= self.cfg.de_full_value:
            logger.warning(
                "DARK ELIXIR FULL (%s >= %s) — bot berhenti & tutup CoC",
                value,
                self.cfg.de_full_value,
            )
            try:
                self.deps.adb.shell(self.device, f"am force-stop {self.cfg.coc_package}")
                logger.info("CoC ditutup")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Gagal menutup CoC: %s", exc)
            return True
        return False

    def _army_ready(self) -> bool:
        """Validasi deck: tipe strict wajib terdeteksi + jumlah dragon (badge).

        Prioritas: deteksi template kartu (akurat lintas akun, tahan perbedaan
        urutan/jumlah hero) lalu ``cards.verify_deck`` (tipe di ``deck_strict_types``;
        tipe tanpa template/komposisi nol bersifat soft). Bila deteksi kosong-total,
        jatuh ke cek template lama (dragon_card.png/balloon_card.png). Badge jumlah
        dragon tetap dicek; jumlah lain hanya dicatat.
        """
        shot = self._capture("army_check.png")
        if shot is None:
            return True
        img = self._img(shot)
        detected: dict = {}
        if self.cfg.card_detection:
            tpl_dir = self.assets / "simplicity" / "deck"
            if tpl_dir.is_dir():
                try:
                    detected = cards.detect_cards(
                        img, tpl_dir, threshold=self.cfg.card_threshold
                    )
                except Exception as exc:  # noqa: BLE001 - deteksi tak boleh mematikan loop
                    logger.info("Deck scan gagal (%s); pakai cek template lama", exc)
                    detected = {}
        if detected:
            tpl_dir = self.assets / "simplicity" / "deck"
            try:
                available = cards.available_keys(tpl_dir) if tpl_dir.is_dir() else None
                check = cards.verify_deck(
                    detected,
                    self.cfg.army,
                    list(self.cfg.deck_strict_types),
                    extra_template=self.cfg.extra_troop_template,
                    available=available,
                )
            except Exception as exc:  # noqa: BLE001 - verifikasi tak boleh mematikan loop
                logger.warning("Deck check gagal (%s); pakai cek template lama", exc)
                detected = {}
            else:
                if check.soft_missing:
                    logger.info(
                        "Deck check: soft (tak tersedia/tak diwajibkan): %s",
                        check.soft_missing,
                    )
                if not check.ok:
                    logger.warning(
                        "Deck TIDAK sesuai (tipe hilang: %s; terdeteksi: %s)",
                        check.problems, sorted(detected),
                    )
                    return False
                logger.info("Deck check LOLOS (strict: %s)", check.notes.get("ok", []))
                self._log_card_counts(img, detected)
        if not detected:
            for template in ("dragon_card.png", "balloon_card.png"):
                path = self.assets / template
                if not path.is_file():
                    continue
                try:
                    match = self.deps.find_template(img, path, 0.85)
                except ValueError:
                    continue
                if not match.found:
                    logger.warning(
                        "Deck tidak sesuai simpanan bot (kartu %s tak ketemu, skor %.2f)",
                        template.replace("_card.png", ""),
                        match.score,
                    )
                    return False
        crop = self.deps.crop_percent(img, *self.cfg.army_badge_roi)
        value = self.deps.read_badge(crop)
        expected = int(self.cfg.army.get("dragon_drops", 0))
        if value is None:
            logger.info("Jumlah tak terbaca, tapi kartu sudah sesuai - lanjut")
            return True
        logger.info("Cek pasukan: dragon x%d (harap x%d)", value, expected)
        if expected > 0:
            return value >= expected
        return value >= 2

    def _log_card_counts(self, img, detected: dict) -> None:
        """Catat jumlah pasukan/spell dari badge kartu (info saja, best-effort)."""
        for key in ("balloon", self.cfg.extra_troop_template, "rage", "freeze"):
            if not key or key not in detected:
                continue
            try:
                cx, cy, _score = detected[key]
                x1, y1, x2, y2 = cards.count_roi(cx, cy)
                value = self.deps.read_badge(img[y1:y2, x1:x2])
            except Exception as exc:  # noqa: BLE001 - info jumlah tak boleh mematikan gate
                logger.info("Info jumlah %s: gagal dibaca (%s)", key, exc)
                continue
            logger.info("Info jumlah %s: %s", key, value)

    def _army_gate(self) -> StepResult:
        """Validasi deck begitu lawan tampil; mismatch → end battle + home."""
        if self._army_ready():
            return StepResult(True)
        logger.warning("Pasukan tidak sesuai simpanan bot - end battle utk latih ulang")
        self.actions.tap_percent(*self.cfg.end_battle_point)
        self.deps.sleep(0.2)
        self.actions.tap_percent(*self.cfg.confirm_point)
        self.deps.sleep(2)
        return StepResult(False, "army_mismatch")

    def _recover_army(self, gate: StepResult) -> StepResult:
        """Perbaiki deck langsung dari layar scout: Deck Builder presisi atau recipe."""
        ui_ready = bool(self.cfg.train_ui and "army_button" in self.cfg.train_ui)
        has_clear = (
            any(
                self.cfg.train_ui.get(key) is not None
                for key in ("clear_troops", "clear_spells", "clear_siege")
            )
            if ui_ready
            else False
        )
        rounds = 2 if has_clear else 1
        for _ in range(rounds):
            if self.deps.should_stop():
                return StepResult(False, "stopped by user")
            if ui_ready and self._build_army():
                gate = self._army_gate()
                if gate.ok:
                    logger.info("Deck presisi siap - lanjut serang")
                    return gate
                continue
            if self.cfg.train_points and self._train_army():
                return self._army_gate()
            return gate
        return gate

    PANEL_CAP_ROI = [0.42, 0.208, 0.515, 0.248]

    def _panel_capacity(self) -> int | None:
        """Baca 'terpakai/352' di panel My Army; None bila tak terbaca."""
        shot = self._capture("panel_cap.png")
        if shot is None:
            return None
        crop = self.deps.crop_percent(self._img(shot), *self.PANEL_CAP_ROI)
        value = self.deps.read_de(crop)
        if value is None:
            return None
        if value > 999:
            return value // 1000
        if 300 <= value <= 400:
            return 0
        return value

    def _waits_for_menu(self, tries: int = 6) -> bool:
        """True bila layar menu multiplayer terlihat (ada tombol Find a Match)."""
        for _ in range(tries):
            shot = self._capture("menu_check.png")
            if shot is not None and self._match_safe(shot, "find_match.png").found:
                return True
            self.deps.sleep(1.0)
        return False

    def _build_army(self) -> bool:
        """Deck Builder: mode RESEP (stabil) atau mode BANGUN (klik sesuai data GUI)."""
        ui = self.cfg.train_ui
        if not ui or "army_button" not in ui:
            logger.info("train_ui belum dikalibrasi - pakai train_points/manual")
            return False
        has_recipe = ui.get("recipe_tab") is not None and ui.get("recipe_use") is not None
        has_grid = bool(ui.get("grid"))
        use_recipe = self.cfg.train_mode == "quick_train"
        if use_recipe and not has_recipe:
            logger.info("Mode resep dipilih tapi belum dikalibrasi - fallback ke mode bangun")
            use_recipe = False
        elif not use_recipe and not has_grid and has_recipe:
            logger.info("Mode bangun tanpa grid - fallback ke mode resep")
            use_recipe = True
        self.actions.tap_percent(*ui["army_button"])
        logger.info("Deck Builder: buka panel (mode %s)", "resep" if use_recipe else "bangun")
        self.deps.sleep(2.5)
        if use_recipe:
            self.actions.tap_percent(*ui["recipe_tab"])
            logger.info("Deck Builder: tab Saved Recipes")
            self.deps.sleep(1.5)
            self.actions.tap_percent(*ui["recipe_use"])
            logger.info("Deck Builder: Use resep tersimpan")
            self.deps.sleep(2.5)
            if ui.get("recipe_confirm") is not None:
                self.actions.tap_percent(*ui["recipe_confirm"])
                logger.info("Deck Builder: konfirmasi Use Recipe (Okay)")
                self.deps.sleep(2.0)
            if ui.get("close_button") is not None:
                self.actions.tap_percent(*ui["close_button"])
                self.deps.sleep(2.0)
            return True
        for key in ("clear_troops", "clear_spells", "clear_siege"):
            point = ui.get(key)
            if point is None:
                continue
            self.actions.tap_percent(*point)
            logger.info("Deck Builder: clear %s", key)
            self.deps.sleep(1.3)
            if ui.get("clear_okay") is not None:
                self.actions.tap_percent(*ui["clear_okay"])
                self.deps.sleep(1.5)
        self.actions.tap_percent(0.5913, 0.3333)  # buka daftar troop
        self.deps.sleep(2.0)
        built = 0
        for group, point in ui.get("grid", {}).items():
            if group in ("rage_spell", "freeze_spell"):
                continue
            count = int(self.cfg.army.get(group, 0))
            if count <= 0:
                continue
            for _ in range(count):
                if self.deps.should_stop():
                    return False
                self.actions.tap_percent(*point)
                self.deps.sleep(0.45)
            built += count
            logger.info("Deck Builder: +%d %s", count, group)
        spell_points = {
            g: ui["grid"][g]
            for g in ("rage_spell", "freeze_spell")
            if g in ui.get("grid", {})
        }
        if spell_points and ui.get("spell_edit") is not None:
            self.actions.tap_percent(*ui["spell_edit"])
            logger.info("Deck Builder: buka daftar spell")
            self.deps.sleep(2.0)
            for group, point in spell_points.items():
                count = int(self.cfg.army.get(group, 0))
                if count <= 0:
                    continue
                for _ in range(count):
                    if self.deps.should_stop():
                        return False
                    self.actions.tap_percent(*point)
                    self.deps.sleep(0.45)
                built += count
                logger.info("Deck Builder: +%d %s", count, group)
        logger.info("Deck Builder: %d unit diklik; tutup panel", built)
        if ui.get("close_button") is not None:
            self.actions.tap_percent(*ui["close_button"])
            self.deps.sleep(2.0)
        return True

    def _train_army(self) -> bool:
        """Klik urutan latih tersimpan (buka Army -> resep -> Train -> tutup) lalu tunggu."""
        if not self.cfg.train_points:
            logger.info("train_points kosong - latih pasukan manual lalu start lagi")
            return False
        logger.info("Melatih pasukan otomatis (%d klik)", len(self.cfg.train_points))
        for xp, yp in self.cfg.train_points:
            if self.deps.should_stop():
                return False
            self.actions.tap_percent(xp, yp)
            self.deps.sleep(1.2)
        total = self.cfg.train_wait_s
        if total <= 0:
            return True
        logger.info("Latihan diantrekan - tunggu sampai %d detik", total)
        waited = 0
        while waited < total:
            if self.deps.should_stop():
                return False
            step = min(30, total - waited)
            self.deps.sleep(step)
            waited += step
        return True

    # -- steps -----------------------------------------------------------

    def connect(self) -> StepResult:
        self._state(BotState.CONNECT)
        try:
            self.device = self.deps.adb.connect(self.cfg.device_address)
        except AdbError as exc:
            return StepResult(False, f"adb connect failed: {exc}")
        logger.info("Connected to %s", self.device)
        return StepResult(True)

    def prepare(self) -> StepResult:
        self._state(BotState.PREPARE)
        width, height = self.deps.adb.wm_size(self.device)
        logger.info("Screen %dx%d", width, height)
        self.actions = self.deps.actions_factory(
            self.deps.adb, self.device, self.mode, (width, height)
        )
        self._size = (width, height)
        self.workdir = Path(self.cfg.workdir) / _safe_dir_name(self.device)
        self.workdir.mkdir(parents=True, exist_ok=True)
        return StepResult(True)

    def find_attack(self) -> StepResult:
        self._state(BotState.FIND_ATTACK)
        deadline = self.deps.monotonic() + self.cfg.find_attack_timeout_s
        while True:
            if self.deps.should_stop():
                return StepResult(False, "stopped by user")
            shot = self._capture("screen.png")
            if shot is None:
                return StepResult(False, "attack screen capture failed")
            if self._handle_popups(shot):
                continue
            match = self._match(shot, "attack.png")
            if match.found:
                logger.info("Attack button found (score %.2f)", match.score)
                return StepResult(True, data={"px": match.cx, "py": match.cy})
            if (
                self._match_safe(shot, "returnhome.png").found
                or self._match_safe(shot, "claim_reward.png").found
                or self._match_safe(shot, "continue.png").found
            ):
                logger.info("Not home yet (result dialogs visible); sweeping to home")
                self._tap_until_home(max_rounds=6)
                continue
            if not self._coc_running():
                self._launch_coc()
                deadline = self.deps.monotonic() + max(self.cfg.find_attack_timeout_s, 120)
                continue
            if self.deps.monotonic() > deadline:
                return StepResult(False, "attack button not found (timeout)")
            logger.info("Attack button not visible yet; waiting...")
            self.deps.sleep(3)

    def matchmaking(self) -> StepResult:
        self._state(BotState.MATCHMAKING)
        deadline = self.deps.monotonic() + self.cfg.search_timeout_s
        clicked = False
        while True:
            if self.deps.should_stop():
                return StepResult(False, "stopped by user")
            if not self._ensure_coc():
                return StepResult(False, "coc_restarted")
            shot = self._capture("matchmaking.png")
            if shot is None:
                return StepResult(False, "matchmaking capture failed")
            if self._handle_popups(shot):
                continue
            if not clicked:
                match = self._match(shot, "find_match.png")
                if match.found:
                    self.actions.tap_px(match.cx, match.cy)
                    logger.info("Click Find Match")
                    self.deps.sleep(1.0)
                    confirm_shot = self._capture("matchmaking_confirm.png")
                    if confirm_shot is not None:
                        confirm = self._match_safe(confirm_shot, "attack2.png")
                        if confirm.found:
                            self.actions.tap_px(confirm.cx, confirm.cy)
                            logger.info("Click Attack (confirm)")
                            self.deps.sleep(1.0)
                    clicked = True
                    continue
            if self._match_safe(shot, "next.png").found:
                logger.info("Opponent found (Next button visible)")
                return StepResult(True)
            if self.deps.monotonic() > deadline:
                return StepResult(False, "opponent search timeout")
            if clicked:
                logger.info("Searching opponent...")
            self.deps.sleep(2)

    def _read_once(self, roi: list[float]) -> int | None:
        shot = self._capture("loot.png")
        if shot is None:
            return None
        crop = self.deps.crop_percent(self._img(shot), *roi)
        return self.deps.read_loot(crop)

    def _read_verified(self, roi: list[float]) -> int | None:
        """Two reads must agree (template digit reader); retry once on failure."""
        for _ in range(2):
            value = self._read_once(roi)
            if value is None:
                self.deps.sleep(1.0)
                continue
            confirm = self._read_once(roi)
            if confirm == value:
                return value
            logger.info("Loot read mismatch (%s vs %s); retrying", value, confirm)
            self.deps.sleep(1.0)
        return None

    def evaluate_loot(self) -> StepResult:
        self._state(BotState.LOOT_CHECK)
        self.deps.sleep(self.cfg.loot_settle_s)
        gold = self._read_verified(self.cfg.loot_roi)
        elixir = (
            self._read_verified(self.cfg.loot_roi_elixir) if gold is not None else None
        )
        dark = None
        if gold is not None and elixir is not None and self.cfg.min_dark > 0:
            dark = self._read_verified(self.cfg.loot_roi_dark)
        if gold is None or elixir is None or (self.cfg.min_dark > 0 and dark is None):
            if self.cfg.on_ocr_fail == "stop":
                return StepResult(False, "OCR unavailable (policy: stop)")
            if self.cfg.on_ocr_fail == "next":
                logger.warning("Loot OCR unavailable; skipping base (policy: next)")
                return StepResult(False, "loot_low")
            logger.warning("OCR unavailable; continuing (policy: attack)")
            return StepResult(True)
        logger.info(
            "Loot: gold %s (min %s) | elixir %s (min %s) | dark %s (min %s)",
            gold,
            self.cfg.min_gold,
            elixir,
            self.cfg.min_elixir,
            dark if dark is not None else "-",
            self.cfg.min_dark,
        )
        if (
            gold >= self.cfg.min_gold
            and elixir >= self.cfg.min_elixir
            and (self.cfg.min_dark == 0 or (dark or 0) >= self.cfg.min_dark)
        ):
            return StepResult(True)
        logger.info(
            "Loot low: gold %s / elixir %s / dark %s below thresholds, continue search",
            gold,
            elixir,
            dark if dark is not None else "-",
        )
        return StepResult(False, "loot_low")

    def click_next(self) -> StepResult:
        for _ in range(self.cfg.next_max_tries):
            shot = self._capture("next.png")
            if shot is not None:
                match = self._match(shot, "next.png")
                if match.found:
                    self.actions.tap_px(match.cx, match.cy)
                    logger.info("Click Next")
                    self.deps.sleep(1.5)
                    return StepResult(True)
            self.deps.sleep(2)
        return StepResult(False, "next button not found")

    _DETECT_KEYS: dict[str, str] = {
        "dragon": "dragon",
        "balloon": "balloon",
        "rage_spell": "rage",
        "freeze_spell": "freeze",
    }

    def _scan_deck(self) -> None:
        """Deteksi posisi kartu deck sekali di awal battle (template matching)."""
        self._deck_cards = {}
        if not self.cfg.card_detection:
            return
        tpl_dir = self.assets / "simplicity" / "deck"
        if not tpl_dir.is_dir():
            return
        shot = self._capture("deck_scan.png")
        if shot is None:
            return
        try:
            self._deck_cards = cards.detect_cards(
                self._img(shot), tpl_dir, threshold=self.cfg.card_threshold
            )
        except Exception as exc:  # noqa: BLE001 - deteksi tidak boleh mematikan loop
            logger.warning("Deck scan gagal: %s", exc)
            self._deck_cards = {}
        if self._deck_cards:
            logger.info(
                "Deck terdeteksi: %s",
                ", ".join(
                    f"{key}@({x},{y}) {score:.2f}"
                    for key, (x, y, score) in sorted(self._deck_cards.items())
                ),
            )
        else:
            logger.info("Deck tidak terdeteksi; pakai titik kartu dari konfigurasi")

    def _detected_point(self, key: str | None) -> list[float] | None:
        """Titik persen dari kartu yang terdeteksi (None bila tidak ada)."""
        if not key:
            return None
        hit = self._deck_cards.get(key)
        if hit is None:
            return None
        width, height = self._size
        if width <= 0 or height <= 0:
            return None
        x, y, _score = hit
        return [x / width, y / height]

    def _detected_siege_point(self) -> list[float] | None:
        """Kartu siege terbaik dari kandidat template (blimp/empty/loaded)."""
        best_key: str | None = None
        best_score = 0.0
        for key in cards.SIEGE_KEYS:
            hit = self._deck_cards.get(key)
            if hit is not None and hit[2] > best_score:
                best_key = key
                best_score = hit[2]
        return self._detected_point(best_key)

    def _jittered(self, xp, yp):
        width, height = self._size
        if self.cfg.deploy_jitter_px <= 0 or width <= 0 or height <= 0:
            return [xp, yp]
        jx = self.cfg.deploy_jitter_px / width
        jy = self.cfg.deploy_jitter_px * 0.7 / height
        return jitter_point(xp, yp, jx, jy)

    def _deploy_delay(self):
        delay = self.cfg.tap_delay_ms / 1000
        pct = self.cfg.tap_delay_jitter_pct / 100
        if pct > 0:
            delay *= random.uniform(1 - pct, 1 + pct)
        return delay

    def _drop_group(
        self,
        card_key: str,
        points: list,
        count: int | None = None,
        card_point: list[float] | None = None,
    ) -> None:
        if not points:
            return
        point: list[float] | None = None
        if card_key == "wall_wrecker":
            point = self._detected_siege_point()
        detect_key = self._DETECT_KEYS.get(card_key)
        if card_key == "extra_troop":
            detect_key = self.cfg.extra_troop_template
        if point is None:
            point = self._detected_point(detect_key)
        if point is None:
            point = (
                card_point
                if card_point is not None
                else self.cfg.card_points.get(card_key)
            )
        if point is None:
            logger.warning("Titik kartu %s tidak dikenal; grup dilewati", card_key)
            return
        self.actions.tap_percent(*point)
        logger.info("Select %s card", card_key)
        self.deps.sleep(0.5)
        taps = len(points) if count is None else max(count, 0)
        for i in range(taps):
            xp, yp = points[i % len(points)]
            self.actions.tap_percent(*self._jittered(xp, yp))
            self.deps.sleep(self._deploy_delay())

    def _drop_heroes(self, chosen) -> None:
        if not chosen.hero_positions:
            logger.info("Scenario has no hero positions; heroes skipped")
            return
        detected = [
            point
            for point in (self._detected_point(key) for key in cards.HERO_KEYS)
            if point is not None
        ]
        card_list: list = detected if detected else list(self.cfg.hero_cards)
        if not card_list:
            return
        for i, card in enumerate(card_list):
            xp, yp = chosen.hero_positions[i % len(chosen.hero_positions)]
            self.actions.tap_percent(*card)
            logger.info("Deploy hero %d", i + 1)
            self.deps.sleep(0.4)
            self.actions.tap_percent(*self._jittered(xp, yp))
            self.deps.sleep(self._deploy_delay())

    def attack(self) -> StepResult:
        self._state(BotState.ATTACK)
        self._scan_deck()
        strategies: list = []
        try:
            strategies = self.deps.load_strategies(self.cfg.strategy_file)
        except Exception as exc:  # noqa: BLE001 - fall back to the legacy drop
            logger.warning("Strategy load failed (%s); using legacy single drop", exc)

        if strategies:
            if self.cfg.mirror_strategies:
                strategies = strategies + [mirror_strategy(s) for s in strategies]
            chosen = random.choice(strategies)
            logger.info("Executing Scenario: %s", chosen.name)
            army = self.cfg.army
            if chosen.wall_wrecker_drop is not None:
                self._drop_group(
                    "wall_wrecker",
                    [chosen.wall_wrecker_drop],
                    count=army.get("wall_wrecker_drop", 1),
                )
            self._drop_group("dragon", chosen.dragon_drops, count=army.get("dragon_drops"))
            self._drop_group(
                "balloon", chosen.balloon_drops, count=army.get("balloon_drops")
            )
            extra_count = army.get("extra_troop", 0)
            if self.cfg.extra_troop_card is not None and extra_count > 0:
                self._drop_group(
                    "extra_troop",
                    chosen.dragon_drops,
                    count=extra_count,
                    card_point=self.cfg.extra_troop_card,
                )
            self._drop_heroes(chosen)
            if self.cfg.rage_card is not None:
                self._drop_group(
                    "rage_spell",
                    chosen.rage_spell_positions,
                    count=army.get("rage_spell"),
                    card_point=self.cfg.rage_card,
                )
            if self.cfg.freeze_card is not None:
                self._drop_group(
                    "freeze_spell",
                    chosen.freeze_spell_positions,
                    count=army.get("freeze_spell"),
                    card_point=self.cfg.freeze_card,
                )
        else:
            logger.info("No strategies loaded; legacy single drop")
            self.actions.tap_percent(*self.cfg.drop_card_point)
            self.deps.sleep(0.5)
            for xp, yp in self.cfg.drop_points:
                self.actions.tap_percent(xp, yp)
                self.deps.sleep(self.cfg.tap_delay_ms / 1000)

        if self.cfg.speed_up_taps > 0:
            for _ in range(self.cfg.speed_up_taps):
                self.actions.tap_percent(*self.cfg.speed_up_point)
                self.deps.sleep(0.5)
            logger.info("Speed up x%d", 2 ** self.cfg.speed_up_taps)

        logger.info("Waiting up to %d s for battle end", self.cfg.end_delay_s)
        hero_delays = set(self.cfg.hero_skill_delays_s)
        ended_early = False
        for second in range(max(self.cfg.end_delay_s, 1)):
            if self.deps.should_stop():
                return StepResult(False, "stopped by user")
            self.deps.sleep(1)
            if second in hero_delays and self.cfg.hero_skill_points:
                for xp, yp in self.cfg.hero_skill_points:
                    self.actions.tap_percent(xp, yp)
                logger.info("Trigger hero skills (t=%ds)", second)
            if second % 5 == 4:
                if not self._ensure_coc():
                    return StepResult(False, "coc_restarted")
                shot = self._capture("battle_end.png")
                if shot is not None:
                    if self._handle_popups(shot):
                        continue
                    if (
                        self._match_safe(shot, "returnhome.png").found
                        or self._match_safe(shot, "claim_reward.png").found
                    ):
                        ended_early = True
                        logger.info("Battle ended early (results screen visible)")
                        break
        if not ended_early:
            self.actions.tap_percent(*self.cfg.end_battle_point)
            logger.info("Click End Battle")
            self.deps.sleep(0.2)
            self.actions.tap_percent(*self.cfg.confirm_point)
            logger.info("Confirm End Battle")
        return StepResult(True)

    def return_home(self) -> StepResult:
        self._state(BotState.RETURN_HOME)
        deadline = self.deps.monotonic() + self.cfg.search_timeout_s
        while True:
            if self.deps.should_stop():
                return StepResult(False, "stopped by user")
            if not self._ensure_coc():
                return StepResult(False, "coc_restarted")
            shot = self._capture("returnhome.png")
            if shot is None:
                return StepResult(False, "return home capture failed")
            if self._match_safe(shot, "returnhome.png").found or self._match_safe(
                shot, "returnhome_event.png"
            ).found:
                break
            claim = self._match_safe(shot, "claim_reward.png")
            if claim.found:
                return self._claim_event_reward(claim)
            if self.deps.monotonic() > deadline:
                return StepResult(False, "return home timeout")
            self.deps.sleep(10)
        self.actions.tap_percent(*self.cfg.return_home_point)
        logger.info("Tap Return Home")
        self.deps.sleep(8)
        if self._tap_until_home():
            return StepResult(True)
        return StepResult(False, "not home after return")

    def _claim_event_reward(self, claim) -> StepResult:
        """Event result screen: Claim Reward -> open chest (4 taps) -> clear dialogs -> home."""
        self.actions.tap_px(claim.cx, claim.cy)
        logger.info("Tap Claim Reward (event chest)")
        self.deps.sleep(2)
        for _ in range(4):
            self.actions.tap_percent(0.5, 0.5)
            self.deps.sleep(1.2)
        logger.info("Chest opened; clearing dialogs until home")
        if self._tap_until_home():
            logger.info("Back home after event claim")
            return StepResult(True)
        return StepResult(False, "event reward: continue failed")

    def _tap_until_home(self, max_rounds: int = 8) -> bool:
        """Tap known dialog buttons (Continue / Claim / Okay / Not Now) until home.

        Blind points cover popups without templates yet: Star Bonus "Okay"
        (star_bonus_point) and Notifications "Not Now" (notifications_not_now_point).
        """
        for _ in range(max_rounds):
            if self.deps.should_stop():
                return False
            shot = self._capture("until_home.png")
            if shot is None:
                self.deps.sleep(2.5)
                continue
            if self._match_safe(shot, "attack.png").found:
                return True
            if self._match_safe(shot, "continue.png").found:
                match = self._match_safe(shot, "continue.png")
                self.actions.tap_px(match.cx, match.cy)
                logger.info("Tap Continue")
            elif self._match_safe(shot, "claim_reward.png").found:
                match = self._match_safe(shot, "claim_reward.png")
                self.actions.tap_px(match.cx, match.cy)
                logger.info("Tap Claim Reward")
            elif self._match_safe(shot, "returnhome.png").found:
                self.actions.tap_percent(*self.cfg.return_home_point)
                logger.info("Tap Return Home")
            else:
                if self._handle_popups(shot):
                    continue
                self.actions.tap_percent(*self.cfg.star_bonus_point)
                logger.info("Tap popup Okay (star bonus point)")
                self.deps.sleep(2.0)
                shot2 = self._capture("until_home.png")
                if shot2 is not None and self._match_safe(shot2, "attack.png").found:
                    return True
                self.actions.tap_percent(*self.cfg.notifications_not_now_point)
                logger.info("Tap Not Now (notifications point)")
            self.deps.sleep(2.5)
        shot = self._capture("until_home.png")
        return shot is not None and self._match_safe(shot, "attack.png").found

    def _run_wall_upgrade(self) -> None:
        """Optional wall upgrade after returning home; failures never break the cycle."""
        try:
            result = wallupgrade.run_wall_upgrade(
                self.cfg.wall_upgrade,
                capture=self._capture,
                load_image=self._img,
                find_template=self._match_safe,
                crop_percent=self.deps.crop_percent,
                ocr_boxes=vision.ocr_text_boxes,
                read_gold=lambda crop: self.deps.ocr_digits(
                    vision.enhance_numeric_crop(crop)
                ),
                tap_px=self.actions.tap_px,
                tap_percent=self.actions.tap_percent,
                swipe_percent=self.actions.swipe_percent,
                sleep=self.deps.sleep,
            )
            logger.info(
                "Wall upgrade: %s%s",
                result.status,
                f" ({result.reason})" if result.reason else "",
            )
        except Exception as exc:  # noqa: BLE001 - optional step, never fatal
            logger.warning("Wall upgrade failed: %s", exc)

    # -- cycle -----------------------------------------------------------

    def run_cycle(self, train_attempts: int = 0, crash_attempts: int = 0) -> StepResult:
        if self.deps.should_stop():
            return StepResult(False, "stopped by user")
        result = self.find_attack()
        if not result.ok:
            return result
        self._collect_resources()
        if self._de_full():
            return StepResult(False, "de_full")
        self.actions.tap_px(result.data["px"], result.data["py"])
        logger.info("Click Attack")
        self.deps.sleep(1.0)
        menu_ok = self._waits_for_menu()
        if not menu_ok:
            logger.warning("Menu multiplayer tidak terdeteksi - builder dilewati")
            try:
                self.deps.adb.shell(self.device, "input keyevent 4")
            except Exception:  # noqa: BLE001
                pass
            self.deps.sleep(1.5)
        if menu_ok and (
            self.cfg.train_mode == "quick_train"
            and self.cfg.train_ui.get("recipe_tab") is not None
            and self.cfg.train_ui.get("recipe_use") is not None
        ):
            if self._build_army():
                logger.info("Deck Builder: pasukan dimuat (mode resep)")
                if not self._waits_for_menu(tries=3):
                    logger.warning("Builder tidak kembali ke menu - tekan BACK")
                    try:
                        self.deps.adb.shell(self.device, "input keyevent 4")
                    except Exception:  # noqa: BLE001
                        pass
                    self.deps.sleep(1.5)
        self.deps.sleep(1.0)

        for _ in range(_MAX_LOOT_ROUNDS):
            if self.deps.should_stop():
                return StepResult(False, "stopped by user")
            result = self.matchmaking()
            if not result.ok:
                if result.reason == "coc_restarted" and crash_attempts < 3:
                    return self.run_cycle(train_attempts, crash_attempts + 1)
                return result
            gate = self._army_gate()
            if not gate.ok:
                gate = self._recover_army(gate)
                if not gate.ok:
                    return gate
            result = self.evaluate_loot()
            if result.ok:
                break
            if result.reason != "loot_low":
                return result
            result = self.click_next()
            if not result.ok:
                return result
        else:
            return StepResult(False, "loot loop limit reached")

        result = self.attack()
        if not result.ok:
            if result.reason == "coc_restarted" and crash_attempts < 3:
                return self.run_cycle(train_attempts, crash_attempts + 1)
            return result
        result = self.return_home()
        if not result.ok and result.reason == "coc_restarted" and crash_attempts < 3:
            return self.run_cycle(train_attempts, crash_attempts + 1)
        if result.ok and self.cfg.wall_upgrade.enabled:
            self._run_wall_upgrade()
        if result.ok:
            self._collect_resources()
            if self._de_full():
                return StepResult(False, "de_full")
        return result


def run(
    config: Config,
    mode: str,
    cycles: int,
    deps: Deps | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> RunSummary:
    """Run `cycles` full bot cycles. Step-level failures come back as a RunSummary."""
    if deps is None:
        deps = _default_deps(config)
    if should_stop is not None:
        deps.should_stop = should_stop
    session = _Session(config, mode, deps)

    result = session.connect()
    if not result.ok:
        return RunSummary(False, 0, result.reason)

    done = 0
    try:
        result = session.prepare()
        if not result.ok:
            return RunSummary(False, 0, result.reason)
        for _ in range(cycles):
            result = session.run_cycle()
            if not result.ok:
                if result.reason == "de_full":
                    return RunSummary(True, done, "DE penuh — bot berhenti")
                if result.reason == "army_mismatch":
                    return RunSummary(
                        True, done, "pasukan tidak sesuai - latih manual / isi train_points"
                    )
                return RunSummary(False, done, result.reason)
            done += 1
    except (AdbError, ValueError, OSError) as exc:
        logger.error("Run aborted: %s", exc)
        return RunSummary(False, done, str(exc))
    session._state(BotState.DONE)
    return RunSummary(True, done, "")
