# coc-lab v2.1 — Desain: Multi-drop Troops + Wall Upgrade (Spec)

- **Status:** approved (design), 2026-10-15 · **Basis:** dossier perilaku `Bot_Crowz_dissection.md` (referensi saja; kode 100% orisinal)
- **Scope malam ini:** (A) strategi multi-drop pasukan + Next-loop penuh, (B) modul wall upgrade (dibangun + di-unit-test; titik/template dikalibrasi live; default nonaktif). Heroes/spells/skills → v2.2.

## A. Strategi multi-drop

- Baru: `coclab/strategy.py`
  - `Strategy(name: str, dragon_drops: list[[x,y]], balloon_drops: list[[x,y]], wall_wrecker_drop: [x,y] | None)`
  - `load_strategies(path) -> list[Strategy]` — validasi: name non-kosong; titik = persen 0..1; minimal satu grup punya titik; `wall_wrecker_drop` null atau titik.
  - File: `AttackStrategies.json` (root proyek) `{"strategies":[...]}`
- `attack()` baru (urutan dari referensi): pilih strategi **acak** → `log "Executing Scenario: <name>"` →
  1. tap `card_points.dragon` → tiap `dragon_drops` (delay `tap_delay_ms`)
  2. tap `card_points.balloon` → tiap `balloon_drops`
  3. jika `wall_wrecker_drop` ada: tap `card_points.wall_wrecker` → tap titik
  4. lanjut: tunggu `end_delay_s` → tap `end_battle_point` → `confirm_point` (flow v1 yang sudah terbukti)
- **Fallback**: file tidak ada / daftar kosong → perilaku v1 (`drop_card_point` + `drop_points`), log jelas.
- Config baru: `strategy_file: str`; `card_points: {dragon, balloon, wall_wrecker}` (masing-masing [x,y] persen).

## B. Wall upgrade (post Return Home)

- Baru: `coclab/wallupgrade.py` + `vision.ocr_text(img) -> str` (engine teks cepat, un-tuk pencarian kata "wall").
- Alur (dari referensi): setelah tap Return Home → jika `wall_upgrade.enabled`:
  1. screenshot home → crop `gold_storage_roi` → `ocr_text`/digit → gold < `gold_min` → berhenti dengan log.
  2. Buka UI wall (template `upgrade_logo`) → klik.
  3. Loop ≤ `max_scroll_tries`: crop `wall_text_roi` → `ocr_text` cari "wall" (case-insensitive); jika ketemu → klik titik → tap `gold_upgrade_point` → `gold_confirm_point` → ulangi pass Elixir (`elixir_upgrade_point`, `elixir_confirm_point`) → selesai; jika tidak → swipe scroll naik → ulang.
- Config baru (semua persen / boolean / int):
  `wall_upgrade: {enabled: false, gold_min, gold_storage_roi[4], upgrade_logo, wall_text_roi[4], gold_upgrade_point, gold_confirm_point, elixir_upgrade_point, elixir_confirm_point, max_scroll_tries}`
- **Kalibrasi live wajib** sebelum `enabled: true` (gold storage + logo_up.png + titik upgrade). Default `false` agar run troops tak terganggu.

## C. Tooling

- Baru: `tools/make_strategy.py` — buka screenshot scout; klik titik per grup (d=dragon, b=balloon, w=wrecker, u=undo, s=simpan); fungsi non-GUI (`save_strategy`, `points_to_percent`) di-unit-test.

## D. Testing

- Unit (tanpa game): loader strategi (valid/invalid), urutan tap multi-drop di-pin via `RecordingAdb` (urutan kartu & titik persis), fallback legacy, `ocr_text` guard, wallupgrade dengan deps fake (gold rendah → skip; "wall" ketemu → urutan tap gold→elixir; max scroll → berhenti).
- Live: (1) **serangan multi-drop terpandu** + sniper (bukti loot/“Troops expanded”), (2) sesi kalibrasi wall bersama operator.

## E. Batasan

- Tidak ada kode CROWZ yang disalin; hanya perilaku/angka dari analisis sendiri.
- Akun uji operator; risiko ToS tetap; `--live` eksplisit.
