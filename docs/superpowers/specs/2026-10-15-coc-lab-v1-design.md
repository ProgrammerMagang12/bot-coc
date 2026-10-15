# coc-lab v1 — Desain Prototipe Otomasi (Spec)

- **Status:** approved (design), 2026-10-15
- **Bahasa implementasi:** Python 3.14 (CLI)
- **Batas etika/legal:** kode 100% original; CROWZ 1.7.1 hanya dipakai sebagai *referensi perilaku* (hasil analisis statis kita sendiri). Template gambar dibuat dari screenshot sendiri. Untuk akun uji milik operator; tidak untuk didistribusikan. Risiko ban ToS Supercell diterima operator.

## 1. Tujuan

Prototipe otomasi end-to-end untuk **testing pribadi** di emulator BlueStacks: menjalankan **satu siklus penuh** — connect → cari lawan → baca loot → serang sederhana → kembali ke home — dengan dua mode: `--observe` (tanpa aksi fisik) dan `--live` (aksi nyata).

## 2. Non-tujuan v1 (menyusul sebagai iterasi)

Multi-drop/strategi JSON kompleks, heroes + spells, wall upgrade, auto zoom-out, multi-emulator, GUI penuh, OCR threshold pintar, mode loop berkelanjutan >N siklus.

## 3. Kriteria sukses v1

1. `py main.py --observe --cycles 1` selesai satu siklus **tanpa aksi fisik**, log berisi setiap state, skor template, dan hasil OCR.
2. `py main.py --live --cycles 1` menyelesaikan satu siklus **dengan aksi nyata** di akun uji (dipandu manual oleh operator).
3. Semua parameter perilaku bisa diubah via `config.json` tanpa mengedit kode.
4. `pytest` lulus untuk unit `vision.find_template` dan matematika persen.
5. Tidak ada loop tak berujung: tiap retry dibatasi; Ctrl+C menghentikan dengan bersih.

## 4. Arsitektur & struktur folder

```
coc-lab/
├─ main.py                 # CLI: --config, --observe|--live, --cycles N, --device
├─ config.example.json     # template konfigurasi (disalin menjadi config.json)
├─ requirements.txt        # opencv-python, numpy, rapidocr-onnxruntime (tahap OCR)
├─ coclab/
│  ├─ __init__.py
│  ├─ config.py            # load + validate config.json → dataclass Config
│  ├─ adb.py               # Adb: connect, devices, screencap, tap, swipe, wm_size
│  ├─ capture.py           # screenshot dengan retry + validasi non-empty
│  ├─ vision.py            # find_template, crop_percent, ocr_digits, is_valid_image
│  ├─ actions.py           # tap/swipe dengan gerbang mode observe|live
│  ├─ state.py             # enum BotState + StepResult(ok, reason, data)
│  └─ loop.py              # orkestrasi state machine v1
├─ tools/
│  └─ make_template.py     # GUI cv2: buka screenshot → selectROI → simpan assets/*.png
├─ assets/                 # template buatan operator (attack.png, find_match.png, ...)
├─ logs/                   # run-YYYYmmdd-HHMMSS.log
├─ tests/
│  └─ test_vision.py       # gambar sintetis; tidak menyentuh game/adb
└─ docs/superpowers/specs/ # dokumen ini
```

**Interfaces inti (kontrak antar-unit):**

| Modul | API |
|---|---|
| `config.py` | `load_config(path) -> Config`; error jelas + baris masalah bila invalid |
| `adb.py` | `Adb(adb_path).connect(addr) -> device_id`; `.screencap(device, dest)`; `.tap(device, x, y)`; `.swipe(device, x1,y1,x2,y2, ms)`; `.wm_size(device) -> (w,h)` |
| `capture.py` | `capture(adb, device, dest, retries=2) -> bool` (validasi via `is_valid_image`) |
| `vision.py` | `find_template(img, tpl, threshold) -> Match(found,cx,cy,score)`; `crop_percent(img, x1,y1,x2,y2) -> ndarray`; `ocr_digits(img) -> int|None`; `is_valid_image(path) -> bool` |
| `actions.py` | `Actions(adb, device, mode)`; `tap_percent(xp,yp,W,H)`; `tap_px(x,y)` — observe ⇒ log `[OBSERVE] ...` saja |
| `loop.py` | `run(config, mode, cycles) -> RunSummary` |

## 5. State machine v1 (semua parameter di config)

| State | Aksi | Default (referensi analisis) | Gagal ⇒ |
|---|---|---|---|
| `CONNECT` | adb connect + resolve device | — | berhenti + pesan |
| `PREPARE` | resolusi via `wm size` (override→physical→fallback) | fallback 1600×900 | fallback dipakai + log |
| `FIND_ATTACK` | cari `attack.png` | threshold 0.69; retry = capture+match ulang ≤3× (jeda 2 s); jeda 1 s setelah klik | berhenti + pesan |
| `MATCHMAKING` | klik → `find_match.png` → klik → tunggu `searching_for_opponents.png` hilang | poll ≤30×2 s | berhenti |
| `LOOT_CHECK` | screenshot → crop ROI loot → OCR | ROI dari config; banding `min_resource` | OCR None ⇒ **berhenti** (default; bisa diubah `on_ocr_fail`) |
| ↳ loot < min | cari `next.png` → klik → ulangi MATCHMAKING | ≤5×2 s | jika tak ada `next.png` ⇒ berhenti |
| `ATTACK` | deploy di `drop_points` berurutan + `tap_delay_ms` → tunggu `end_delay_s` → tap `end_battle_point` → tap `confirm_point` | delay 150 ms/titik; tunggu 200 ms antar tap akhir | berhenti |
| `RETURN_HOME` | tunggu `returnhome(_event).png` → tap `return_home_point` | poll tiap 10 s hingga `search_timeout_s`; jeda akhir 8 s | timeout ⇒ berhenti |

Catatan kalibrasi: v1 memakai satu `threshold` global. Semua angka default (termasuk `loot_roi`, `drop_points`, titik-titik tap) berasal dari analisis referensi dan **wajib dikalibrasi ulang** dengan screenshot nyata milik operator sebelum `--live`.

Catatan: zoom-out **manual** oleh operator sebelum menjalankan (auto zoom-out = v2).

## 6. Mode & pengaman

- `--observe` **(default)**: nol aksi fisik; semua keputusan dan koordinat tercatat di log.
- `--live`: aksi dieksekusi. Wajib disebut eksplisit.
- `--cycles N` default **1**.
- Ctrl+C → stop bersih (tanpa aksi tambahan).
- Semua retry dibatasi; tidak ada `while True` tanpa exit condition selain `cycle loop` yang dibatasi `--cycles`.

## 7. Konfigurasi (contoh)

```json
{
  "adb_path": "D:\\HH\\coc bot\\CROWZ LAB\\CROWZBOT 1.7.1\\adb.exe",
  "device_address": "127.0.0.1:5555",
  "threshold": 0.69,
  "min_resource": 300000,
  "loot_roi": [0.02, 0.05, 0.35, 0.12],
  "on_ocr_fail": "stop",
  "drop_points": [[0.35, 0.72]],
  "tap_delay_ms": 150,
  "end_delay_s": 20,
  "end_battle_point": [0.065, 0.75],
  "confirm_point": [0.614, 0.648],
  "return_home_point": [0.497, 0.849],
  "next_max_tries": 5,
  "search_timeout_s": 60,
  "workdir": "work"
}
```

## 8. Penanganan error

- Tiap state mengembalikan `StepResult`; kegagalan tercatat + alasan; berhenti dengan exit code ≠ 0.
- Screenshot invalid → retry (≤2); ADB error → pesan + berhenti.
- Semua file sementara di `work/<device>/` (nama device dipisah aman).

## 9. Testing

- **Unit (otomatis, tanpa game):** `find_template` (positif/negatif pada gambar sintetis), `crop_percent` math, validasi config.
- **Integrasi manual bertahap:** (a) `make_template` dari screenshot manual → (b) `--observe --cycles 1` sampai semua state benar → (c) `--live --cycles 1` dengan 1 drop point → (d) perluas.
- Game disentuh **hanya** pada langkah manual `--live`.

## 10. Dependensi & prasyarat

- Python 3.14 ✅ (terpasang), `opencv-python` 4.13 ✅ (terpasang), tambahan: `numpy` (bila belum), `rapidocr-onnxruntime` (tahap OCR; pip-only).
- ADB: memakai `adb.exe` yang ditunjuk `adb_path` (default: milik folder CROWZBOT).
- BlueStacks instance "CROWZ 1" di `127.0.0.1:5555`, CoC terpasang, login akun uji.
- Operator menyiapkan template awal dari screenshot sendiri.

## 11. Risiko & batasan

- **ToS/ban** — risiko operator; tidak ada jaminan keamanan.
- Akurasi template bergantung resolusi/muat game; threshold dapat disetel.
- OCR loot bisa salah baca; default fail-safe berhenti.
- v1 sengaja "sederhana": tanpa zoom-out otomatis, tanpa strategi kompleks.

## 12. Referensi parameter

Semua default (§5/§7) berasal dari dossier analisis `Bot_Crowz_dissection.md` (perilaku & angka yang teramati). Implementasi menulis ulang logika dari nol; tidak ada kode dari CROWZ.
