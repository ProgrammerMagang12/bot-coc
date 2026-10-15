# Paket Keandalan — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Memperkuat bot GARUDA dengan verifikasi deck penuh (strict dragon/balloon/extra/rage/freeze), keacakan serang ala Simplicity (jitter + mirror + delay), dan handler popup baru (Another_device tunggu-lanjut, Client_Error relaunch, Connection_lost reconnect).

**Architecture:** Perluasan tiga alur loop yang sudah ada — gate `_army_ready` memakai `cards.verify_deck()` baru; deploy memakai `strategy.jitter_point()`/`strategy.mirror_strategy()`; `_handle_disconnected` diperluas menjadi `_handle_popups` dengan tiga handler baru. Semua bertoggle config dengan fallback ke perilaku lama.

**Tech Stack:** Python 3.14, OpenCV template matching, pytest, ADB (LDPlayer), Tkinter (tidak disentuh).

**Spec:** `docs/superpowers/specs/2026-10-15-paket-keandalan-design.md`

## Global Constraints

- Semua perintah dijalankan dari root worktree: `D:\HH\coc bot\CROWZ LAB\coc-lab-reliability` (branch `feature/reliability-pack`).
- Tes: `py -m pytest -q -p no:cacheprovider` — baseline hijau = 153 tes. Jika worktree dibuat ulang, copy dulu aset fisik (root PNG tak ter-track): `robocopy "D:\HH\coc bot\CROWZ LAB\coc-lab\assets" "assets" /E /NFL /NDL /NJH /NJS`.
- Tidak menyalin kode Simplicity; hanya aset (atribusi sudah ada di `assets/simplicity/NOTICE.md`). Aset baru: `Another_device.png` → `assets/simplicity/ui/Another_device.png`.
- Fallback wajib: setiap fitur baru yang gagal/kosong harus jatuh ke perilaku lama (tanpa exception mematikan loop).
- Gaya commit: `feat:` / `fix:` / `test:` / `docs:` (Conventional Commits, pesan Inggris singkat).
- Threshold template UI mengikuti `cfg.threshold` (0.69); threshold kartu mengikuti `cfg.card_threshold` (0.55).
- Jangan mengubah perilaku: builder/resep, loot OCR, end-battle, return-home, kolektor, wall upgrade, GUI.

## Review Focus

Kelas input/kegagalan yang paling mungkin menggigit dan harus punya tes di task pemiliknya:

1. **Template kartu strict tidak tersedia** (file png hilang) → gate harus SOFT (log), bukan gagal-rebuild berulang. (Task 2 & 3)
2. **Entri `deck_strict_types` tak dikenal** (salah ketik) → diabaikan tanpa crash. (Task 2)
3. **Jitter di tepi peta** (xp≈0.02/0.98, yp≈0.03/0.80) → hasil selalu ter-clamp di batas aman. (Task 4 & 5)
4. **Popup Another_device muncul saat battle-wait** → tidak ada tap liar; alur battle tetap selesai setelah popup hilang. (Task 6)
5. **Stop ditekan saat menunggu Another_device** → berhenti ≤ ~1-2 detik (menunggu dalam potongan 1 detik, cek `should_stop`). (Task 6)

---

### Task 1: Config — 6 field baru

**Files:**
- Modify: `coclab/config.py` (dataclass `Config` + `load_config`)
- Modify: `config.example.json`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces (field dataclass `Config`): `deck_strict_types: list[str]` (default `["dragon","balloon","extra","rage","freeze"]`), `deploy_jitter_px: int` (default 38), `mirror_strategies: bool` (default True), `tap_delay_jitter_pct: int` (default 30, valid 0..90), `another_device_wait_s: int` (default 30, positif), `connection_lost_point: list[float] | None` (default None).

- [ ] **Step 1: Write the failing tests** di `tests/test_config.py`

```python
def test_example_config_reliability_fields():
    cfg = load_config(EXAMPLE)
    assert cfg.deck_strict_types == ["dragon", "balloon", "extra", "rage", "freeze"]
    assert cfg.deploy_jitter_px == 38
    assert cfg.mirror_strategies is True
    assert cfg.tap_delay_jitter_pct == 30
    assert cfg.another_device_wait_s == 30
    assert cfg.connection_lost_point is None


def test_defaults_when_absent(tmp_path):
    import json
    data = json.loads(EXAMPLE.read_text())
    for key in ("deck_strict_types", "deploy_jitter_px", "mirror_strategies",
                "tap_delay_jitter_pct", "another_device_wait_s", "connection_lost_point"):
        data.pop(key, None)
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    cfg = load_config(p)
    assert cfg.deploy_jitter_px == 38 and cfg.mirror_strategies is True


def test_invalid_reliability_fields_rejected(tmp_path):
    import json
    from coclab.config import ConfigError
    import pytest
    base = json.loads(EXAMPLE.read_text())
    for key, bad in (("deploy_jitter_px", -1), ("tap_delay_jitter_pct", 95),
                     ("deck_strict_types", "dragon"), ("another_device_wait_s", 0)):
        data = json.loads(json.dumps(base))
        data[key] = bad
        p = tmp_path / "c.json"
        p.write_text(json.dumps(data))
        with pytest.raises(ConfigError):
            load_config(p)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest tests/test_config.py -q -p no:cacheprovider -k "reliability or defaults_when_absent or invalid_reliability"`
Expected: FAIL (`AttributeError`/`ConfigError` tidak muncul).

- [ ] **Step 3: Implement di `coclab/config.py`**

Dataclass: tambah 6 field setelah `extra_troop_template`. Parsing (dekat `extra_troop_template`):

```python
    strict_raw = data.get("deck_strict_types", ["dragon", "balloon", "extra", "rage", "freeze"])
    if not isinstance(strict_raw, list) or not all(
        isinstance(v, str) and v.strip() for v in strict_raw
    ):
        raise ConfigError("deck_strict_types: expected a list of strings")
    deck_strict_types = [str(v).strip() for v in strict_raw]
    deploy_jitter_px = _nonneg_int(data.get("deploy_jitter_px", 38), "deploy_jitter_px")
    mirror_strategies = _bool(data.get("mirror_strategies", True), "mirror_strategies")
    pct_raw = data.get("tap_delay_jitter_pct", 30)
    if not isinstance(pct_raw, int) or isinstance(pct_raw, bool) or not 0 <= pct_raw <= 90:
        raise ConfigError("tap_delay_jitter_pct: expected an integer between 0 and 90")
    tap_delay_jitter_pct = int(pct_raw)
    another_device_wait_s = _positive_int(
        data.get("another_device_wait_s", 30), "another_device_wait_s"
    )
    lost_raw = data.get("connection_lost_point")
    connection_lost_point = None if lost_raw is None else _point(lost_raw, "connection_lost_point")
```

Lalu teruskan ke konstruktor `Config(...)`.

`config.example.json`: tambah setelah `"extra_troop_template": null,`:

```json
  "deck_strict_types": ["dragon", "balloon", "extra", "rage", "freeze"],
  "deploy_jitter_px": 38,
  "mirror_strategies": true,
  "tap_delay_jitter_pct": 30,
  "another_device_wait_s": 30,
  "connection_lost_point": null,
```

- [ ] **Step 4: Run tests** — `py -m pytest -q -p no:cacheprovider` → semua hijau (153 + 3 baru).

- [ ] **Step 5: Commit** — `git add coclab/config.py config.example.json tests/test_config.py && git commit -m "feat: config fields for reliability pack (gate strict types, jitter, mirror, popup waits)"`

---

### Task 2: `cards.verify_deck` + `available_keys` + `count_roi`

**Files:**
- Modify: `coclab/cards.py`
- Test: `tests/test_cards.py`

**Interfaces:**
- Produces:
  - `@dataclass DeckCheck(ok: bool, problems: list[str], soft_missing: list[str], notes: dict)`
  - `verify_deck(detected: dict[str, tuple[int, int, float]], army: dict[str, int], strict_types: list[str], extra_template: str | None = None, available: set[str] | None = None) -> DeckCheck`
  - `available_keys(templates_dir: str | Path) -> set[str]` — kunci `CARD_FILES` yang file templatenya ada.
  - `count_roi(cx: int, cy: int) -> tuple[int, int, int, int]` — kotak badge jumlah: `(cx-42, cy-74, cx+42, cy-44)`.
  - Konstanta `STRICT_KNOWN = {"dragon", "balloon", "extra", "rage", "freeze"}`.

**Aturan `verify_deck` (final):** untuk tiap tipe di `strict_types` (urutan dipertahankan, duplikat di-skip):
1. tipe tak dikenal → `notes["ignored"] += [tipe]`, lanjut.
2. `extra`: tanpa `extra_template` → `soft_missing += ["extra"]`, lanjut. Kunci = `extra_template`.
3. `rage`/`freeze`: bila `army.get("rage_spell"/"freeze_spell", 0) == 0` → tidak diwajibkan, lanjut.
4. tipe lain: kunci = nama tipe.
5. `available is not None` dan kunci tidak di `available` → `soft_missing += [tipe]`, lanjut.
6. kunci ada di `detected` → `notes["ok"] += [tipe]`; tidak → `problems += [tipe]`.
`ok = not problems`.

- [ ] **Step 1: Write the failing tests** di `tests/test_cards.py`

```python
def test_verify_deck_ok_when_all_strict_present():
    detected = {"dragon": (170, 815, 0.9), "balloon": (291, 815, 0.9),
                "rage": (1180, 815, 0.9), "freeze": (1301, 815, 0.9),
                "extra_pink": (421, 815, 0.9)}
    army = {"rage_spell": 4, "freeze_spell": 3, "extra_troop": 5}
    check = cards.verify_deck(detected, army, ["dragon", "balloon", "extra", "rage", "freeze"],
                              extra_template="extra_pink")
    assert check.ok and check.problems == []


def test_verify_deck_flags_missing_strict_type():
    detected = {"dragon": (170, 815, 0.9), "balloon": (291, 815, 0.9)}
    army = {"rage_spell": 4, "freeze_spell": 3}
    check = cards.verify_deck(detected, army, ["dragon", "balloon", "rage", "freeze"])
    assert not check.ok and check.problems == ["rage", "freeze"]


def test_verify_deck_extra_soft_without_template():
    detected = {"dragon": (0, 0, 0.9), "balloon": (0, 0, 0.9)}
    check = cards.verify_deck(detected, {}, ["dragon", "balloon", "extra"], extra_template=None)
    assert check.ok and check.soft_missing == ["extra"]


def test_verify_deck_rage_not_required_when_zero_comp():
    detected = {"dragon": (0, 0, 0.9), "balloon": (0, 0, 0.9)}
    check = cards.verify_deck(detected, {"rage_spell": 0, "freeze_spell": 0},
                              ["dragon", "balloon", "rage", "freeze"])
    assert check.ok


def test_verify_deck_ignores_unknown_strict_type():
    detected = {"dragon": (0, 0, 0.9), "balloon": (0, 0, 0.9)}
    check = cards.verify_deck(detected, {}, ["dragon", "balloon", "wall_wrecker"])
    assert check.ok and check.notes["ignored"] == ["wall_wrecker"]


def test_verify_deck_template_missing_goes_soft():
    detected = {"dragon": (0, 0, 0.9), "balloon": (0, 0, 0.9)}
    available = {"dragon", "balloon", "rage"}  # freeze tidak tersedia
    check = cards.verify_deck(detected, {"freeze_spell": 3}, ["dragon", "balloon", "freeze"],
                              available=available)
    assert check.ok and check.soft_missing == ["freeze"]


def test_count_roi_around_center():
    x1, y1, x2, y2 = cards.count_roi(170, 815)
    assert (x1, y1, x2, y2) == (128, 741, 212, 771)
```

- [ ] **Step 2: Run tests to verify they fail** — `py -m pytest tests/test_cards.py -q -p no:cacheprovider` → FAIL `verify_deck` tidak ada.

- [ ] **Step 3: Implement di `coclab/cards.py`** — sesuai aturan final di atas. `count_roi` = aritmetika langsung. `available_keys`:

```python
def available_keys(templates_dir: str | Path) -> set[str]:
    """Kunci kartu yang file templatenya benar-benar ada di folder."""
    directory = Path(templates_dir)
    return {name for name, filename in CARD_FILES.items() if (directory / filename).is_file()}
```

- [ ] **Step 4: Run tests** → hijau.

- [ ] **Step 5: Commit** — `git add coclab/cards.py tests/test_cards.py && git commit -m "feat: verify_deck gate logic + available_keys + count_roi"`

---

### Task 3: Gate v2 di loop (`_army_ready`)

**Files:**
- Modify: `coclab/loop.py` (`_army_ready`)
- Test: `tests/test_loop.py`

**Interfaces:**
- Consumes: `cards.verify_deck`, `cards.available_keys`, `cards.count_roi` (Task 2); `cfg.deck_strict_types`, `cfg.extra_troop_template`, `cfg.card_detection`, `cfg.card_threshold` (Task 1).
- Produces: perilaku gate — deteksi non-kosong → `verify_deck`; gagal → `return False`; lolos → badge dragon (≥ `army.dragon_drops`) + info badge balloon/extra/rage/freeze (log saja). Deteksi kosong-total → fallback lama (dragon_card/balloon_card @0.85).

- [ ] **Step 1: Write the failing tests** di `tests/test_loop.py`

```python
def test_gate_strict_miss_ends_battle(monkeypatch):
    """rage/freeze strict hilang dari deteksi → end battle + tidak serang."""
    from coclab import loop as loop_mod
    from coclab.vision import Match
    monkeypatch.setattr(
        loop_mod.cards, "detect_cards",
        lambda img, tpl_dir, **kw: {"dragon": (170, 815, 0.9), "balloon": (291, 815, 0.9)},
    )
    states = []
    deps, adb = make_deps(full_script(), states)
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert (104, 675) in adb.taps  # end_battle_point (0.065, 0.75)
    assert "ATTACK" not in states or states.count("ATTACK") == 0


def test_gate_strict_pass_attacks(monkeypatch):
    from coclab import loop as loop_mod
    hits = {"dragon": (170, 815, 0.9), "balloon": (291, 815, 0.9),
            "rage": (1180, 815, 0.9), "freeze": (1301, 815, 0.9)}
    monkeypatch.setattr(loop_mod.cards, "detect_cards", lambda img, tpl_dir, **kw: dict(hits))
    states = []
    deps, adb = make_deps(full_script(), states)
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok and "ATTACK" in states
    assert (104, 675) not in adb.taps
```

Catatan: EXAMPLE army punya `rage_spell: 4`, `freeze_spell: 3`; `extra_troop: 2` tapi `extra_troop_template` null → extra otomatis soft.

- [ ] **Step 2: Run tests to verify they fail** — `py -m pytest tests/test_loop.py -q -p no:cacheprovider -k "gate_strict"` → FAIL (gate lama lolos karena monkeypatch baru tidak mengubah jalur lama).

- [ ] **Step 3: Implement `_army_ready`** — ganti blok `if detected:` dengan:

```python
        if detected:
            tpl_dir = self.assets / "simplicity" / "deck"
            available = cards.available_keys(tpl_dir) if tpl_dir.is_dir() else None
            check = cards.verify_deck(
                detected,
                self.cfg.army,
                list(self.cfg.deck_strict_types),
                extra_template=self.cfg.extra_troop_template,
                available=available,
            )
            if check.soft_missing:
                logger.info("Deck check: soft (tak tersedia/tak diwajibkan): %s", check.soft_missing)
            if not check.ok:
                logger.warning(
                    "Deck TIDAK sesuai (tipe hilang: %s; terdeteksi: %s)",
                    check.problems, sorted(detected),
                )
                return False
            logger.info("Deck check LOLOS (strict: %s)", check.notes.get("ok", []))
            self._log_card_counts(img, detected)
        if not detected:
            # fallback lama dipertahankan apa adanya
            for template in ("dragon_card.png", "balloon_card.png"):
                ...
```

Dan helper baru `_log_card_counts(self, img, detected)`: untuk kunci `("balloon", self.cfg.extra_troop_template, "rage", "freeze")` (skip None), bila ada di `detected`: crop `cards.count_roi(cx, cy)` → `self.deps.read_badge(crop)` → `logger.info("Info jumlah %s: %s", key, value)` — semua dibungkus `try/except Exception` (best-effort, tidak menggagalkan).

- [ ] **Step 4: Run tests** — `py -m pytest -q -p no:cacheprovider` → hijau (termasuk tes gate lama tetap lulus: jalur fallback utuh).

- [ ] **Step 5: Commit** — `git commit -am "feat: army gate v2 uses strict deck verification with informational counts"`

---

### Task 4: `strategy.jitter_point` + `strategy.mirror_strategy`

**Files:**
- Modify: `coclab/strategy.py`
- Test: `tests/test_strategy.py`

**Interfaces:**
- Produces:
  - `jitter_point(xp: float, yp: float, jitter_x: float, jitter_y: float, rng=None) -> list[float]` — xp/yp persen; `jitter_x`/`jitter_y` = magnitudo maksimum dalam fraksi layar; horizontal bias ke tengah peta (xp≤0.5 → +, else −); vertikal ke atas (`yp - uniform(0, jitter_y)`); clamp `x∈[0.02,0.98]`, `y∈[0.03,0.80]`; `rng` default `random` module.
  - `mirror_strategy(strategy: Strategy) -> Strategy` — salinan dengan semua titik peta `x → 1 - x` (dragon, balloon, wall_wrecker_drop, hero_positions, rage/freeze positions).

- [ ] **Step 1: Write the failing tests** di `tests/test_strategy.py`

```python
import random

from coclab.strategy import Strategy, jitter_point, mirror_strategy


def test_jitter_point_zero_returns_same():
    assert jitter_point(0.3, 0.4, 0.0, 0.0) == [0.3, 0.4]


def test_jitter_point_direction_toward_center():
    rng = random.Random(1)
    right = jitter_point(0.2, 0.5, 0.03, 0.03, rng=rng)
    assert right[0] >= 0.2 and right[1] <= 0.5
    left = jitter_point(0.8, 0.5, 0.03, 0.03, rng=rng)
    assert left[0] <= 0.8 and left[1] <= 0.5


def test_jitter_point_clamped_at_edges():
    rng = random.Random(2)
    for _ in range(200):
        x, y = jitter_point(0.021, 0.031, 0.03, 0.03, rng=rng)
        assert 0.02 <= x <= 0.98 and 0.03 <= y <= 0.80


def test_mirror_strategy_flips_all_points():
    s = Strategy(
        name="a", dragon_drops=[[0.1, 0.4]], balloon_drops=[[0.2, 0.3]],
        wall_wrecker_drop=[0.3, 0.35], hero_positions=[[0.4, 0.5]],
        rage_spell_positions=[[0.15, 0.2]], freeze_spell_positions=[[0.25, 0.25]],
    )
    m = mirror_strategy(s)
    assert m.name == "a" and m.dragon_drops == [[0.9, 0.4]]
    assert m.balloon_drops == [[0.8, 0.3]] and m.wall_wrecker_drop == [0.7, 0.35]
    assert m.hero_positions == [[0.6, 0.5]]
    assert m.rage_spell_positions == [[0.85, 0.2]]
    assert m.freeze_spell_positions == [[0.75, 0.25]]


def test_mirror_strategy_none_wrecker_kept_none():
    s = Strategy(name="b", dragon_drops=[[0.1, 0.4]], balloon_drops=[], wall_wrecker_drop=None)
    assert mirror_strategy(s).wall_wrecker_drop is None
```

- [ ] **Step 2: Run to verify fail** — `py -m pytest tests/test_strategy.py -q -p no:cacheprovider -k "jitter or mirror"` → FAIL import.

- [ ] **Step 3: Implement** di `coclab/strategy.py` (fungsi module-level, `import random` di atas):

```python
def jitter_point(xp, yp, jitter_x, jitter_y, rng=None):
    """Geser titik peta ala Simplicity: horizontal ke arah tengah, vertikal ke atas."""
    r = rng or random
    direction = 1.0 if xp <= 0.5 else -1.0
    x2 = xp + direction * r.uniform(0, jitter_x)
    y2 = yp - r.uniform(0, jitter_y)
    return [min(0.98, max(0.02, x2)), min(0.80, max(0.03, y2))]


def _mirror_points(points):  # list[[x, y]] -> list[[1-x, y]]
    return [[1.0 - x, y] for x, y in points]


def mirror_strategy(strategy):
    """Salinan cermin kiri↔kanan (x -> 1-x) dari sebuah Strategy."""
    return Strategy(
        name=strategy.name,
        dragon_drops=_mirror_points(strategy.dragon_drops),
        balloon_drops=_mirror_points(strategy.balloon_drops),
        wall_wrecker_drop=(None if strategy.wall_wrecker_drop is None
                           else [1.0 - strategy.wall_wrecker_drop[0], strategy.wall_wrecker_drop[1]]),
        hero_positions=_mirror_points(strategy.hero_positions),
        rage_spell_positions=_mirror_points(strategy.rage_spell_positions),
        freeze_spell_positions=_mirror_points(strategy.freeze_spell_positions),
    )
```

- [ ] **Step 4: Run tests** → hijau.

- [ ] **Step 5: Commit** — `git commit -am "feat: jitter_point + mirror_strategy for attack variance"`

---

### Task 5: Integrasi keacakan ke deploy (loop)

**Files:**
- Modify: `coclab/loop.py` (import strategy names, helper `_jittered`/`_deploy_delay`, `_drop_group`, `_drop_heroes`, `attack()`)
- Test: `tests/test_loop.py`

**Interfaces:**
- Consumes: `strategy.jitter_point`, `strategy.mirror_strategy` (Task 4); config Task 1.
- Produces: `_Session._jittered(xp, yp) -> list[float]` (jitter via `cfg.deploy_jitter_px` & `self._size`, faktor vertikal 0.7); `_Session._deploy_delay() -> float` (basis `tap_delay_ms` ± `tap_delay_jitter_pct`); mirror diterapkan di `attack()` sebelum `random.choice`.

- [ ] **Step 1: Write the failing tests** di `tests/test_loop.py`

```python
def _run_with_strategy(monkeypatch, tmp_config=None, strategy=None, script=None):
    from coclab.strategy import Strategy
    st = strategy or Strategy(
        name="t", dragon_drops=[[0.5, 0.5]], balloon_drops=[[0.55, 0.5]],
        wall_wrecker_drop=[0.3, 0.55], hero_positions=[[0.6, 0.5]],
        rage_spell_positions=[[0.7, 0.5]], freeze_spell_positions=[[0.8, 0.5]])
    states = []
    deps, adb = make_deps(script or full_script(), states)
    deps.load_strategies = lambda path: [st]
    cfg = load_config(tmp_config or EXAMPLE)
    summary = run(cfg, "observe", 1, deps=deps)
    return summary, adb, states


def test_jitter_applied_to_map_drops(tmp_path):
    import json
    data = json.loads(EXAMPLE.read_text())
    data["mirror_strategies"] = False  # fokus jitter; cermin diuji terpisah
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    summary, adb, _ = _run_with_strategy(None, tmp_config=p)
    assert summary.ok
    # dragon [0.5,0.5] → arah + : tx ∈ [800, 839], ty ∈ [423, 450]
    assert any(800 <= tx <= 840 and 421 <= ty <= 450 for tx, ty in adb.taps)
    # balloon [0.55,0.5] → arah − (ke tengah): tx ∈ [842, 880], ty ∈ [423, 450]
    assert any(842 <= tx <= 880 and 421 <= ty <= 450 for tx, ty in adb.taps)


def test_jitter_zero_taps_exact(tmp_path):
    import json
    data = json.loads(EXAMPLE.read_text())
    data["deploy_jitter_px"] = 0
    data["mirror_strategies"] = False
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    summary, adb, _ = _run_with_strategy(None, tmp_config=p)
    assert summary.ok
    assert (800, 450) in adb.taps      # dragon [0.5, 0.5] persis
    assert (880, 450) in adb.taps      # balloon [0.55, 0.5] persis


def test_mirror_picks_mirrored_scenario(monkeypatch):
    from coclab import loop as loop_mod
    from coclab.strategy import Strategy
    mirrored_dragon = [[0.1, 0.5]]
    st = Strategy(name="m", dragon_drops=mirrored_dragon, balloon_drops=[],
                  wall_wrecker_drop=None, hero_positions=[], rage_spell_positions=[],
                  freeze_spell_positions=[])
    monkeypatch.setattr(loop_mod.random, "choice", lambda seq: seq[-1])  # cermin di akhir
    summary, adb, _ = _run_with_strategy(None, strategy=st)
    assert summary.ok
    # asli [0.1] → cermin [0.9]: tx ∈ [1440−38, 1440]
    assert any(1402 <= tx <= 1441 and 421 <= ty <= 450 for tx, ty in adb.taps)
```

- [ ] **Step 2: Run to verify fail** — FAIL (tap masih persis).

- [ ] **Step 2b: Perbarui tes lama `test_attack_uses_detected_card_positions`** — setelah jitter aktif, tes ini pecah (assert presisi `(800, 450)`). Ubah agar memakai config tmp (json dari EXAMPLE → tmp_path) dengan `"deploy_jitter_px": 0` dan `"mirror_strategies": false`; assert lain (posisi kartu deteksi ±2px) tetap apa adanya.

- [ ] **Step 3: Implement di `coclab/loop.py`**

- Import: `from coclab.strategy import jitter_point, load_strategies as load_strategies_default, mirror_strategy`.
- Helper baru:

```python
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
```

- `_drop_group`: tap unit → `self.actions.tap_percent(*self._jittered(xp, yp))`; `self.deps.sleep(self._deploy_delay())`.
- `_drop_heroes`: tap posisi hero → jitter sama; delay `_deploy_delay()`.
- `attack()`: setelah `strategies = self.deps.load_strategies(...)` dan sebelum `random.choice`:

```python
            if self.cfg.mirror_strategies:
                strategies = strategies + [mirror_strategy(s) for s in strategies]
```

- [ ] **Step 4: Run tests** → hijau penuh.

- [ ] **Step 5: Commit** — `git commit -am "feat: jittered deploy taps, delay jitter, mirrored attack scenarios"`

---

### Task 6: Handler popup (`_handle_popups`) + aset

**Files:**
- Modify: `coclab/loop.py` (rename/extend handler, call sites)
- Create: `assets/simplicity/ui/Another_device.png` (copy dari `D:\HH\coc bot\auto-farm-bot\Simplicity v3.50.0\Templates\Another_device.png`)
- Test: `tests/test_loop.py`

**Interfaces:**
- Consumes: config `another_device_wait_s`, `connection_lost_point` (Task 1); aset `simplicity/ui/Another_device.png`, `simplicity/ui/Client_error!.png`, `simplicity/ui/Connection_lost.png`.
- Produces: `_Session._handle_popups(shot) -> bool` (menggantikan pemanggilan `_handle_disconnected`); sub-handler `_handle_afk_reload` (isi lama), `_handle_another_device`, `_handle_client_error`, `_handle_connection_lost`.

- [ ] **Step 1: Copy aset & audit**

```powershell
Copy-Item 'D:\HH\coc bot\auto-farm-bot\Simplicity v3.50.0\Templates\Another_device.png' assets\simplicity\ui\Another_device.png -Force
py -c "from coclab.vision import is_valid_image; import pathlib; [print(p.name, is_valid_image(p)) for p in pathlib.Path('assets/simplicity/ui').glob('*') if p.name in ('Another_device.png','Client_error!.png','Connection_lost.png')]"
```

Expected: ketiganya `True`.

- [ ] **Step 2: Write the failing tests** di `tests/test_loop.py`

```python
def test_another_device_waits_during_battle_without_tap():
    """Popup muncul SAAT battle-wait (setelah STATE ATTACK) → tidak tap, tunggu, lanjut."""
    from coclab.vision import Match
    script = full_script()
    seen = {"n": 0}
    states = []
    deps, adb = make_deps(script, states)
    base_ft = deps.find_template

    def ft(img, tpl, threshold):
        from pathlib import Path
        if Path(tpl).name == "Another_device.png":
            if "ATTACK" in states:          # hanya muncul saat battle-wait
                seen["n"] += 1
                return Match(seen["n"] <= 2, 500, 400, 0.99)
            return Match(False, 0, 0, 0.0)
        return base_ft(img, tpl, threshold)

    deps.find_template = ft
    sleeps = []
    base_sleep = deps.sleep
    deps.sleep = lambda s: sleeps.append(s) or base_sleep(s)
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok and seen["n"] >= 3
    assert not any(abs(tx - 500) <= 3 and abs(ty - 400) <= 3 for tx, ty in adb.taps)
    assert sleeps.count(1.0) >= 2  # menunggu dalam potongan 1 detik


def test_another_device_stop_is_responsive():
    from coclab.vision import Match
    deps, adb = make_deps(full_script(), [])
    base_ft = deps.find_template
    state = {"stops": 0}

    def ft(img, tpl, threshold):
        from pathlib import Path
        if Path(tpl).name == "Another_device.png":
            return Match(True, 500, 400, 0.99)
        return base_ft(img, tpl, threshold)

    deps.find_template = ft
    deps.should_stop = lambda: state.__setitem__("stops", state["stops"] + 1) or state["stops"] > 2
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert not summary.ok and "stopped" in summary.reason.lower()


def test_client_error_restarts_coc():
    from coclab.vision import Match
    script = full_script(**{"Client_error!.png": Match(True, 500, 400, 0.99)})
    seen = {"n": 0}
    deps, adb = make_deps(script, [])
    base_ft = deps.find_template

    def ft(img, tpl, threshold):
        from pathlib import Path
        if Path(tpl).name == "Client_error!.png":
            seen["n"] += 1
            return Match(seen["n"] <= 1, 500, 400, 0.99)
        return base_ft(img, tpl, threshold)

    deps.find_template = ft
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok
    assert any("am start" in c for c in adb.shells)


def test_connection_lost_taps_reconnect_point(tmp_path):
    import json
    data = json.loads(EXAMPLE.read_text())
    data["connection_lost_point"] = [0.5, 0.55]
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    from coclab.vision import Match
    script = full_script(**{"Connection_lost.png": Match(True, 500, 400, 0.99)})
    seen = {"n": 0}
    deps, adb = make_deps(script, [])
    base_ft = deps.find_template

    def ft(img, tpl, threshold):
        from pathlib import Path
        if Path(tpl).name == "Connection_lost.png":
            seen["n"] += 1
            return Match(seen["n"] <= 1, 500, 400, 0.99)
        return base_ft(img, tpl, threshold)

    deps.find_template = ft
    summary = run(load_config(p), "observe", 1, deps=deps)
    assert summary.ok and (800, 495) in adb.taps
```

- [ ] **Step 3: Run to verify fail** — FAIL (handler belum ada / template tidak pernah dicek).

- [ ] **Step 4: Implement di `coclab/loop.py`**

- Rename isi `_handle_disconnected` lama → `_handle_afk_reload` (logika OCR + cluster TIDAK berubah).
- Handler baru:

```python
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
```

- Ganti semua pemanggilan `self._handle_disconnected(shot)` → `self._handle_popups(shot)`; semua 4 call-site sudah ada: `find_attack` (~baris 524), `matchmaking` (~559), loop tunggu battle di `attack()` (~851), dan `return_home` (~937) — tidak ada yang perlu ditambah.
- **Perbarui 2 unit test lama** di `tests/test_loop.py` (~baris 330 & 342) yang memanggil `session._handle_disconnected(None)` → `session._handle_popups(None)`; semantik tes tidak berubah (RELOAD ditemukan → True; tidak ada apa-apa → False).
- Catatan urutan: Another_device dicek SEBELUM Client_error/Connection_lost.

- [ ] **Step 5: Run tests** → hijau penuh.

- [ ] **Step 6: Commit** — `git add -A && git commit -m "feat: popup handlers (another-device wait, client-error relaunch, connection-lost reconnect)"`

---

### Task 7: Kalibrasi & verifikasi pra-merge

**Files:**
- Verify/patch bila perlu: `coclab/cards.py` (konstanta `count_roi`), `assets/simplicity/deck/*` (template), config
- Test: `tests/test_cards.py` (tes tambahan bila konstanta berubah)

**Langkah (bukan TDD klasik — verifikasi empiris, hasil = bukti):**

- [ ] **Step 1: Verifikasi `count_roi` & badge dragon**

```powershell
py -c "
import cv2
from coclab import cards
from coclab.digits import read_badge_number
img = cv2.imread(r'D:\HH\coc bot\CROWZ LAB\coc-lab\work\dev\hcb3_menu.png', cv2.IMREAD_COLOR)
hits = cards.detect_cards(img, 'assets/simplicity/deck', threshold=0.55)
cx, cy, _ = hits['dragon']
x1, y1, x2, y2 = cards.count_roi(cx, cy)
print('badge dragon:', read_badge_number(img[y1:y2, x1:x2]))
"
```
Expected: `13`. Jika bukan → geser konstanta `count_roi` dan ulangi; update tes `test_count_roi_around_center` bila berubah.

- [ ] **Step 2: Verifikasi strict templates di Shreyas (screenshot run lama)**

```powershell
py -c "
import cv2, glob
from coclab import cards
files = sorted(glob.glob(r'D:\HH\coc bot\CROWZ LAB\coc-lab\work\dev\run1[0-4]_*.png'))[-40:]
best = {}
for f in files:
    img = cv2.imread(f)
    if img is None or img.shape[:2] != (900, 1600): continue
    hits = cards.detect_cards(img, 'assets/simplicity/deck', threshold=0.4)
    for k, (x, y, s) in hits.items():
        if s > best.get(k, (0, 0, 0))[2]: best[k] = (x, y, s)
for k in sorted(best): print(k, round(best[k][2], 3))
"
```
Expected: `dragon`, `balloon`, `rage`, `freeze` muncul dengan skor ≥ 0.55 di screenshot Shreyas. Jika rage/freeze < 0.55 → (a) cari frame yang lebih jelas, (b) kalau tetap rendah: laporkan ke pengguna + jatuhkan sementara dari `deck_strict_types` profil (tanpa ubah kode).

- [ ] **Step 3: E2E live 1 siklus (HCBNJ, 5557)**

Prasyarat: LDPlayer index 1 jalan, CoC di home. Jalankan dari main repo (profil dist ada di sana) dengan `coclab` diambil dari worktree:

```powershell
cd 'D:\HH\coc bot\CROWZ LAB\coc-lab'
$env:PYTHONPATH = 'D:\HH\coc bot\CROWZ LAB\coc-lab-reliability'
cmd /c "py work\dev\e2e_hcbnj_live.py > work\dev\e2e_reliability.log 2>&1"
```

(`sys.path[0]` = folder script, jadi `coclab` resolve dari PYTHONPATH=worktree; profil dibaca dari `dist\GARUDA\profiles\HCBNJ.json`; aset dari `assets` relatif cwd — template `Another_device.png` belum ada di main sampai merge → `_popup_match` akan aman mengembalikan False.)

Expected log: `Deck check LOLOS (strict: [...])`, tap berada dalam jitter, battle selesai, `RunSummary(ok=True)`; tidak ada end-battle akibat gate.

- [ ] **Step 4: (Opsional, bila sempat) uji popup Another_device live** — login HCBNJ dari HP saat bot menunggu; amati: bot tidak tap, menunggu; setelah logout dari HP, alur lanjut. Catat hasil di komentar commit/issue; kalau popup ternyata butuh tap reload → tambahkan `another_device_reload_point` sesuai spec.

- [ ] **Step 5: Commit hasil kalibrasi (bila ada perubahan konstanta/aset)** — `git commit -am "test: calibrate count_roi and verify strict templates on real screenshots"`

---

### Task 8: Zoom-out normalization (pinch sendevent sebelum attack + di home)

**Files:**
- Create: `coclab/pinch.py`
- Modify: `coclab/loop.py` (`attack()`, `find_attack()`, `_Session.__init__`), `coclab/config.py`, `config.example.json`
- Test: `tests/test_pinch.py` (baru), `tests/test_loop.py`, `tests/test_config.py`

**Interfaces:**
- `coclab/pinch.py` (murni, tanpa I/O):
  - `TOUCH_DEVICE = "/dev/input/event4"` (touchscreen LDPlayer: ABS_MT 1:1 dengan 1600x900 — terverifikasi spike), `REMOTE_PATH = "/data/local/tmp/coclab_pinch_out.sh"`.
  - `build_pinch_out_script(width=1600, height=900, steps=5, device=TOUCH_DEVICE) -> str` — skrip shell sendevent pinch-close 2 jari vertikal: jari0 `(cx, cy-150) → (cx, cy-40)`, jari1 `(cx, cy+150) → (cx, cy+40)`; kode: EV_ABS=3 / EV_KEY=1 / EV_SYN=0; ABS_MT_SLOT=47, ABS_MT_TRACKING_ID=57, ABS_MT_POSITION_X=53, ABS_MT_POSITION_Y=54, BTN_TOUCH=330, SYN_REPORT=0; `sleep 0.06` antar langkah; diakhiri TRACKING_ID -1 (kedua slot) + BTN_TOUCH 0 + SYN.
  - `write_script_cmd(path=REMOTE_PATH, script=None) -> str` — perintah satu-baris via adb shell: `cat > PATH << 'COCLAB_EOF'` + skrip + `COCLAB_EOF` + `chmod 755 PATH` (heredoc; aman karena skrip tanpa kutip tunggal).
- `coclab/config.py` fields baru: `zoom_out_enabled: bool` (default True), `zoom_out_pinches: int` (default 3, valid 0..10), `zoom_out_settle_s: float` (default 0.8, nonneg).
- `_Session`: flag `self._pinch_ready = False`; method `_zoom_out()` — bila enabled & pinches>0: tulis skrip sekali (cache `_pinch_ready`) → `adb.shell(f"sh {REMOTE_PATH}")` x pinches → `sleep(zoom_out_settle_s)` → log; SEMUA exception ditelan + `logger.warning("Zoom-out gagal (lanjut): %s", exc)`.
- Hook 1: `attack()` — setelah `self._state(BotState.ATTACK)`, SEBELUM `self._scan_deck()` → `self._zoom_out()`.
- Hook 2: `find_attack()` — di dalam blok `if match.found:` sebelum `return StepResult(True, ...)` → `self._zoom_out()` (home).
- `config.example.json`: 3 key baru (`true`, `3`, `0.8`).

- [ ] **Step 1: Write the failing tests** — `tests/test_pinch.py`:

```python
from coclab import pinch


def test_script_has_two_fingers_and_converging_moves():
    s = pinch.build_pinch_out_script()
    assert f"sendevent {pinch.TOUCH_DEVICE} 3 47 0" in s   # slot 0 turun
    assert f"sendevent {pinch.TOUCH_DEVICE} 3 47 1" in s   # slot 1 turun
    assert " 410" in s and " 490" in s                     # posisi akhir jari (saling mendekat)
    assert s.count(" 330 1") == 1 and s.count(" 330 0") == 1  # BTN_TOUCH down/up


def test_script_downs_ups_and_syn():
    s = pinch.build_pinch_out_script(steps=3)
    assert f"sendevent {pinch.TOUCH_DEVICE} 0 0 0" in s          # SYN_REPORT
    assert f"sendevent {pinch.TOUCH_DEVICE} 3 57 -1" in s        # tracking up
    assert s.startswith("sendevent")


def test_write_cmd_heredoc():
    cmd = pinch.write_script_cmd()
    assert cmd.startswith("cat > /data/local/tmp/coclab_pinch_out.sh << 'COCLAB_EOF'")
    assert "chmod 755 /data/local/tmp/coclab_pinch_out.sh" in cmd
```

dan `tests/test_loop.py`:

```python
def test_zoom_out_before_attack_and_at_home():
    from coclab import pinch
    deps, adb = make_deps(full_script(), [])
    summary = run(load_config(EXAMPLE), "observe", 1, deps=deps)
    assert summary.ok
    sh = f"sh {pinch.REMOTE_PATH}"
    assert adb.shells.count(sh) >= 6  # 3x di find_attack (home) + 3x di attack()
    assert any(pinch.REMOTE_PATH in c and "cat >" in c for c in adb.shells)


def test_zoom_out_disabled(tmp_path):
    import json
    data = json.loads(EXAMPLE.read_text())
    data["zoom_out_enabled"] = False
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data))
    deps, adb = make_deps(full_script(), [])
    summary = run(load_config(p), "observe", 1, deps=deps)
    assert summary.ok
    assert not any("coclab_pinch_out.sh" in c for c in adb.shells)
```

dan `tests/test_config.py`: defaults (`True`, `3`, `0.8`) + tolak `zoom_out_pinches` 11 / `zoom_out_settle_s` -1.

- [ ] **Step 2: Run to verify RED** — `py -m pytest tests/test_pinch.py tests/test_loop.py -q -p no:cacheprovider -k "pinch or zoom"` → FAIL (modul belum ada).

- [ ] **Step 3: Implement** `coclab/pinch.py` + config fields + kedua hook loop (sesuai Interfaces).

- [ ] **Step 4: Run full suite** — `py -m pytest -q -p no:cacheprovider` → 178 + ~7 baru hijau.

- [ ] **Step 5: Commit** — `git add coclab/pinch.py coclab/loop.py coclab/config.py config.example.json tests/ && git commit -m "feat: zoom-out normalization via sendevent pinch (before attack and at home)"`

---

### Task 9: Merge, rebuild EXE, verifikasi dist

**Files:**
- Modify (di main repo): `dist/GARUDA/config.json`, `dist/GARUDA/profiles/*.json` (tambahan key baru — defaults cukup, tapi ditulis eksplisit)
- Rebuild: `dist\GARUDA\GARUDA.exe` + aset

- [ ] **Step 1: Push branch & merge ke main**

```powershell
cd 'D:\HH\coc bot\CROWZ LAB\coc-lab-reliability'
git push -u origin feature/reliability-pack
cd 'D:\HH\coc bot\CROWZ LAB\coc-lab'
git merge --no-ff feature/reliability-pack -m "merge: paket keandalan (gate v2, keacakan serang, handler popup)"
cmd /c "py -m pytest -q -p no:cacheprovider"  # 153+ hijau di main
git push origin main
```

- [ ] **Step 2: Update config dist & profil**

```powershell
py -c "
import json
from pathlib import Path
for p in [Path(r'dist\GARUDA\config.json'), Path(r'config.json')]:
    if p.is_file():
        d = json.loads(p.read_text(encoding='utf-8'))
        d.setdefault('deck_strict_types', ['dragon','balloon','extra','rage','freeze'])
        d.setdefault('deploy_jitter_px', 38)
        d.setdefault('mirror_strategies', True)
        d.setdefault('tap_delay_jitter_pct', 30)
        d.setdefault('another_device_wait_s', 30)
        d.setdefault('connection_lost_point', None)
        p.write_text(json.dumps(d, indent=2), encoding='utf-8')
        print(p, 'OK')
"
```

- [ ] **Step 3: Rebuild EXE** — di main repo, perintah persis seperti rebuild terakhir:

```powershell
cd 'D:\HH\coc bot\CROWZ LAB\coc-lab'
for ($i = 0; $i -lt 15; $i++) {
    $p = Get-Process GARUDA -ErrorAction SilentlyContinue
    if (-not $p) { break }
    $p | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}
xcopy /E /I /Y dist\GARUDA\profiles dist\_userdata\profiles >$null
if (Test-Path dist\GARUDA\config.json) { cmd /c "copy /Y dist\GARUDA\config.json dist\_userdata\config.json" >$null }
py -m PyInstaller --noconfirm --clean --windowed --name GARUDA --collect-all rapidocr_onnxruntime --collect-all onnxruntime gui.py 2>&1 | Select-Object -Last 1
Copy-Item config.example.json dist\GARUDA\ -Force
Copy-Item AttackStrategies.json dist\GARUDA\ -Force
Copy-Item assets dist\GARUDA\assets -Recurse -Force
xcopy /E /I /Y dist\_userdata\profiles dist\GARUDA\profiles >$null
if (Test-Path dist\_userdata\config.json) { cmd /c "copy /Y dist\_userdata\config.json dist\GARUDA\config.json" >$null }
```

Verifikasi akhir: `dist\GARUDA\assets\simplicity\ui\Another_device.png` ada, `GARUDA.exe` hidup ≥10 detik saat dibuka, lalu ditutup.

- [ ] **Step 4: Commit sisa (bila ada) & push** — semua hijau, branch ter-merge, EXE terverifikasi.

---

## Catatan Eksekusi

- Gunakan TDD persis: tes gagal → implement → hijau → commit per task.
- Setelah semua task: jalankan `py -m pytest -q -p no:cacheprovider` penuh (harus 153 + ±20 tes baru hijau).
- Loop test memakai `tests/fakes.py` yang sudah ada; monkeypatch atribut module (`loop_mod.cards.detect_cards`, `loop_mod.random.choice`, `deps.find_template`) — pola sudah terbukti di `test_attack_uses_detected_card_positions`.
- Jangan menyentuh `dist/` dari worktree — rebuild & update dist dilakukan di main repo (Task 9).
