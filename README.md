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
   Template yang dibutuhkan: **attack, find_match, attack2, next, returnhome, returnhome_event**.
4. Mode aman dulu: `py main.py` atau `py main.py --observe --cycles 1` (observe — tidak ada tap fisik; semua keputusan masuk log).
5. Setelah observe terbukti benar: `py main.py --live --cycles 1` (aksi nyata; mulai dari 1 siklus).

## Struktur

- `coclab/` — `config`, `adb`, `capture`, `vision`, `digits` (pembaca angka template), `actions`, `state`, `loop`
- `gui.py` — **GUI multi-instance**: atur Min Gold/Elixir/Dark + pasukan, Start/Stop per akun (profil di `profiles/`)
- `main.py` — CLI: `--config` (default `config.json`), `--live` (default observe), `--cycles N` (default 1), `--device`
- `tools/make_template.py` — pemilih ROI → template PNG ke `assets/`
- `tools/build_digit_templates.py` — bangun ulang template digit dari frame berlabel
- `tests/` — unit test (tidak menyentuh game/adb nyata)

## GUI (multi-instance)

```
py gui.py
```

- **Tambah** profil → otomatis menyalin `config.json`; satu profil = satu akun/emulator (ubah `Device (adb)`, mis. `127.0.0.1:5557` untuk emulator kedua)
- Ubah **Min Gold / Min Elixir / Min Dark** (0 = abaikan dark), jumlah pasukan, speed-up, cycles → **Simpan**
- **▶ Start** menjalankan bot live per profil secara paralel (multi-instance); **■ Stop** berhenti dengan rapi
- Log tiap instance tampil di panel bawah; status OK/FAILED terlihat di kanan

## Catatan penting

- **Observe default**; `--live` wajib eksplisit. Ctrl+C = stop bersih (exit code 130).
- OCR loot memakai `rapidocr-onnxruntime` bila terpasang; jika tidak ada → kebijakan `on_ocr_fail`
  (default `next` = base dilewati, aman). Angka loot sendiri dibaca oleh **pembaca template digit sendiri**
  (`coclab/digits.py`) — OCR hanya untuk fallback teks lain.
- Speed-up battle: `speed_up_taps` ketukan pada `speed_up_point` setelah deploy penuh (2 ketuk = x4);
  battle berakhir lebih awal terdeteksi → tidak menunggu `end_delay_s` penuh.
- Deploy = **tap kartu** (bar kiri-bawah) → **tap titik di rumPUT**, per pasukan. Tap di atas bangunan = tooltip info (bukan deploy)!
  `tap_delay_ms` mengatur jeda antar-titik; pilihan pasukan TIDAK bertahan setelah battle (tap ulang tiap grup).
- v2: serangan **multi-drop** dari `AttackStrategies.json` (buat dengan `py tools/make_strategy.py --image <scout.png> --name <nama>`); **wall upgrade** opsional via `wall_upgrade.enabled`
  (default `false`; wajib kalibrasi `logo_up.png` + titik-titik dulu). Deploy penuh: `army` (jumlah tap per grup, siklus titik), `hero_cards`, `extra_troop_card`,
  `rage_card`/`freeze_card` (cast di `*_spell_positions`). ⚠️ Posisi kartu hero/spell bergantung **susunan bar pasukan** — kalau jumlah kartu hero berubah
  (mis. hero upgrade selesai/kembali), kalibrasi ulang 4 titik kartu (`hero_cards`, `rage_card`, `freeze_card`, `extra_troop_card`) dari screenshot battle baru.
- Zoom-out masih manual sebelum `--live`.
- Disclaimer lengkap ada di `docs/superpowers/specs/2026-10-15-coc-lab-v1-design.md`.
