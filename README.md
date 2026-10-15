# coc-lab — Prototipe Otomasi (Testing Pribadi)

Prototipe otomasi **original** (kode ditulis sendiri dari nol) untuk satu siklus penuh di emulator:
`cari tombol attack → matchmaking → baca loot (OCR) → banding threshold → serang sederhana → kembali home`.

`CROWZ 1.7.1` hanya dipakai sebagai **referensi perilaku** (hasil analisis statis pribadi); tidak ada kode atau aset dari sana.

> ⚠️ **Peringatan** — otomasi game (Clash of Clans) melanggar ToS Supercell dan berisiko **ban permanen** pada akunmu.
> Gunakan hanya di akun/emulator uji milikmu sendiri. Jangan didistribusikan. Jangan untuk jual jasa/farming.

## Prasyarat

- Windows + Python (jalankan lewat `py`): `py -m pip install -r requirements.txt`
- ADB (`adb.exe`) — isi `adb_path` pada config (default menunjuk folder CROWZBOT)
- Emulator (mis. BlueStacks) dengan game terpasang + login akun uji
- Hubungkan: `adb connect 127.0.0.1:5555` (sesuaikan `device_address`)

## Langkah pakai

1. `copy config.example.json config.json`, lalu **kalibrasi semua angka** dengan screenshot nyatamu —
   terutama `loot_roi`, `drop_points`, `end_battle_point`, `confirm_point`, `return_home_point`.
2. Pastikan `adb devices` menampilkan device berstatus `device`.
3. Buat template dari screenshot sendiri (mis. screenshot di `work/<device>/`):
   `py tools/make_template.py --image work/.../screen.png --name attack`
   Template yang dibutuhkan: **attack, find_match, searching_for_opponents, next, returnhome, returnhome_event**.
4. Mode aman dulu: `py main.py` (observe — tidak ada tap fisik; semua keputusan masuk log).
5. Setelah observe terbukti benar: `py main.py --live --cycles 1` (aksi nyata; mulai dari 1 siklus).

## Struktur

- `coclab/` — `config`, `adb`, `capture`, `vision`, `actions`, `state`, `loop`
- `main.py` — CLI: `--config` (default `config.json`), `--live` (default observe), `--cycles N` (default 1), `--device`
- `tools/make_template.py` — pemilih ROI → template PNG ke `assets/`
- `tests/` — unit test (tidak menyentuh game/adb nyata)

## Catatan penting

- **Observe default**; `--live` wajib eksplisit. Ctrl+C = stop bersih (exit code 130).
- OCR loot memakai `rapidocr-onnxruntime` bila terpasang; jika tidak ada → kebijakan `on_ocr_fail`
  (default `stop` = berhenti, aman).
- v1 belum termasuk: zoom-out otomatis (lakukan manual sebelum `--live`), strategi multi-drop,
  heroes/spells, wall upgrade — direncanakan sebagai iterasi berikutnya.
- Disclaimer lengkap ada di `docs/superpowers/specs/2026-10-15-coc-lab-v1-design.md`.
