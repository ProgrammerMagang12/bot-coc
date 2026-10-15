# Paket Keandalan — Desain (Sub-proyek A)

Tanggal: 2026-10-15
Status: disetujui untuk implementasi (setelah review spec ini)
Ruang lingkup: tiga peningkatan keandalan serangan bot GARUDA (coclab).
Branch: `feature/reliability-pack` (worktree `coc-lab-reliability`).

## Ringkasan

Tiga bagian yang memperkuat alur serangan yang sudah ada, tanpa mengubah
perilaku dasar yang sudah terbukti (builder resep, loot OCR, end battle,
return home):

1. **Verifikasi deck penuh** — gate army memverifikasi semua tipe kartu yang
   diwajibkan (dragon, balloon, extra, rage, freeze) alih-alih dragon+balloon.
2. **Keacakan serang** — jitter titik drop di peta + mirror strategi
   kiri↔kanan + variasi delay antar-tap (agresif ala Simplicity).
3. **Handler popup** — `Another_device` (tunggu lalu lanjut otomatis),
   `Client_Error!` (relaunch), `Connection_lost` (reconnect).

## Konteks & kondisi awal

- Kartu deck sudah dideteksi otomatis via template matching
  (`coclab/cards.py`, aset `assets/simplicity/deck/`, threshold config).
- Gate army sekarang: cek keberadaan `dragon_card.png`/`balloon_card.png`
  (template lama, 0.85) ATAU deteksi baru (dragon + balloon), plus badge
  jumlah dragon.
- Deploy memakai posisi kartu hasil deteksi (fallback ke config lama).
- Kayuhan referensi: Simplicity v3.50.0 `attacks/attacks.py` memakai jitter
  terarah (`dx` menuju tengah peta, `dy` ke atas) dan memilih sisi
  kiri/kanan secara acak; implementasi di sini adalah kode sendiri.

## Bagian 1 — Verifikasi Deck Penuh (gate v2)

### Modul

Fungsi murni baru di `coclab/cards.py`:

```python
@dataclass
class DeckCheck:
    ok: bool                  # True = boleh lanjut serang
    problems: list[str]       # tipe wajib yang tidak terdeteksi
    soft_missing: list[str]   # tipe strict yang templatenya tidak tersedia
    notes: dict               # info tambahan utk log

def verify_deck(
    detected: dict[str, tuple[int, int, float]],
    army: dict[str, int],
    strict_types: list[str],
    extra_template: str | None = None,
) -> DeckCheck
```

### Aturan

- Pemetaan tipe → kunci deteksi: `dragon`→`dragon`, `balloon`→`balloon`,
  `extra`→nilai `extra_troop_template`, `rage`→`rage`, `freeze`→`freeze`.
- Tipe di `strict_types` wajib terdeteksi, KECUALI:
  - `extra` tanpa `extra_troop_template` → otomatis soft (catat saja);
  - `rage`/`freeze` yang komposisinya 0 (`army.rage_spell`/`freeze_spell` = 0)
    → tidak diwajibkan;
  - template tidak ada di aset → otomatis soft untuk sesi itu.
- `ok = not problems` (problems = tipe wajib yang hilang).
- Jumlah: TIDAK di `verify_deck`. Di loop, cek badge jumlah dragon tetap
  seperti sekarang (nilai ≥ `army.dragon_drops`, tak terbaca = lolos +
  warning). Tambahan informasional: badge balloon/extra/rage/freeze dibaca
  best-effort lalu DICATAT di log (tidak menggagalkan).

### Integrasi loop (`_army_ready`)

- Alur baru: capture → `cards.detect_cards(...)` → `cards.verify_deck(...)`.
  - `ok` False → warning + `return False` (jalur lama: end battle + rebuild).
  - `ok` True → cek badge dragon + pembacaan info badge lain → `True`.
- Fallback: bila folder template tidak ada / deteksi kosong-total →
  jalur lama (template `dragon_card.png`/`balloon_card.png` @0.85).
- `_recover_army` yang sudah ada otomatis mengecek ulang setelah rebuild.

### Config baru

- `deck_strict_types` (default `["dragon","balloon","extra","rage","freeze"]`).
  Nilai tak dikenal diabaikan + warning. Daftar ini bisa dilonggarkan tanpa
  rebuild EXE bila ada template yang bermasalah di satu akun.

### Kalibrasi wajib sebelum selesai

- Verifikasi template `rage`/`freeze` (dan `extra`) terhadap deck akun
  **Shreyas** memakai screenshot run lama di `work/dev/` + satu scout live;
  bila skor di bawah threshold → perbaiki aset/titik daripada menyerahkan
  gate yang salah blokir.

### Tes

- Unit `verify_deck`: lolos; tipe hilang → problems; extra tanpa template →
  soft; rage=0 di komposisi → tidak diwajibkan; strict_types tak dikenal →
  diabaikan.
- Loop (fake deps + monkeypatch deteksi): strict miss → end battle dipanggil;
  strict lolos + soft bolong → serang lanjut.

## Bagian 2 — Keacakan Serang

### Config baru

| key | default | arti |
|---|---|---|
| `deploy_jitter_px` | 38 | magnitudo jitter titik peta (0 = mati) |
| `mirror_strategies` | true | sertakan versi cermin tiap skenario |
| `tap_delay_jitter_pct` | 30 | variasi delay antar-tap (±%) |

### Jitter (hanya titik PETA)

- Fungsi `jitter_point(xp, yp, jitter_px, rng=None)`:
  - horizontal: `dx = uniform(0, jitter_px)` dengan arah = tanda `(0.5 - xp)`
    (selalu menuju tengah peta; xp = 0.5 → positif);
  - vertikal: `dy = -uniform(0, 0.7 * jitter_px)` (ke atas, meniru pola
    Simplicity);
  - clamp hasil: `xp ∈ [0.02, 0.98]`, `yp ∈ [0.03, 0.80]`.
- Diterapkan pada: tap unit di `_drop_group` (titik drop skenario) dan tap
  posisi hero di `_drop_heroes`.
- TIDAK diterapkan pada: tap kartu (posisi hasil deteksi), tombol UI
  (End Battle, confirm, return home, speed-up, collect), dialog.

### Mirror

- Fungsi `mirror_strategy(strategy) -> Strategy` di `coclab/strategy.py`:
  semua titik (`dragon_drops`, `balloon_drops`, `wall_wrecker_drop`,
  `hero_positions`, `rage_spell_positions`, `freeze_spell_positions`)
  dikonversi `x → 1 - x`.
- Di `attack()`: bila `mirror_strategies`, daftar pilihan diperluas dengan
  versi cermin setiap skenario sebelum `random.choice`.

### Delay

- Delay antar-unit (drop loop & hero) = `tap_delay_ms/1000 *
  uniform(1 - pct/100, 1 + pct/100)`.
- Sleep struktural lain (tunggu battle, konfirmasi, dsb.) tidak diubah.

### Tes

- Unit jitter: hasil selalu dalam clamp; arah dx benar (kiri→+ , kanan→−);
  `jitter_px=0` → titik tidak berubah; deterministik via `rng` ber-seed.
- Unit mirror: konversi titik benar (termasuk `wall_wrecker_drop` None).
- Loop: tap hasil drop berada dalam toleransi jitter; dengan mirror aktif,
  titik drop bisa muncul di sisi kanan (assert berbasis seed).

## Bagian 3 — Handler Popup

### Aset

- Copy `Another_device.png` dari Simplicity ke `assets/simplicity/ui/`
  (+ audit `Client_error!.png` dan `Connection_lost.png` yang sudah dicopy;
  tambah yang kurang). Verifikasi visual 1600×900.

### Handler (`_handle_popups`, perluasan `_handle_disconnected`)

Urutan cek tiap capture (semua call-site lama tetap):

1. **AFK RELOAD GAME** (eksisting, tidak berubah).
2. **Another_device** — log warning + `sleep(another_device_wait_s)` (default
   30) + `return True`. Tidak ada tap. Bila popup masih ada, iterasi berikut
   menunggu lagi; begitu hilang, alur lanjut otomatis. Tidak merebut sesi.
3. **Client_Error!** — diperlakukan seperti crash: `am force-stop` +
   `_launch_coc()` + return True.
4. **Connection_lost** — tap titik reconnect (`connection_lost_point` baru;
   default `[0.5, 0.5]` — titik tengah dialog — final saat kalibrasi) +
   sleep 10 + return True.

### Config baru

- `another_device_wait_s` (default 30).
- `connection_lost_point` (opsional; null = pakai default internal).

### Kalibrasi wajib sebelum selesai

- Uji live: login dari HP saat bot jalan → amati popup Another_device
  (apakah hilang sendiri saat HP logout, atau butuh 1 tap). Hasilnya
  menentukan apakah perlu `another_device_reload_point` (tap tunggu lama).
  Sampai terverifikasi, handler memilih TIDAK tap apa pun (sesuai pilihan
  pengguna: tunggu & lanjut otomatis).
- Uji `Connection_lost` bila muncul alami; kalau tidak, minimal verifikasi
  template & titik terhadap dialog asli dari screenshot Simplicity.

### Tes

- Loop: script fake memuat `Another_device.png` → tidak ada tap, sleep
  wait_s dipanggil, alur lanjut saat template hilang.
- Loop: `Client_Error!` → `am start` dipanggil (shells berisi am start).
- Loop: `Connection_lost` → tap connection_lost_point terjadi.

## Non-goals

- Tidak mengubah builder/resep, loot OCR, end-battle, return-home, kolektor,
  wall upgrade, GUI (selain baris log yang sudah ada).
- Tidak menyalin kode Simplicity; hanya aset (dengan atribusi `NOTICE.md`).

## Kriteria sukses

1. Tes lama (153) tetap hijau + tes baru untuk ketiga bagian.
2. Verifikasi template strict di HCBNJ (live) dan Shreyas (screenshot)
   selesai; tidak ada false-fail pada dua akun.
3. E2E live 1 siklus di HCBNJ: log menunjukkan cek deck strict + jitter
   terpakai (tap dalam toleransi) + tanpa regresi (loot → serang → home).
4. EXE di-rebuild, dist berisi aset baru, smoke test lulus.
5. Branch di-push dan di-merge ke `main` setelah semua di atas lulus.

## Risiko & mitigasi

| Risiko | Mitigasi |
|---|---|
| Template rage/freeze false-fail di akun tertentu | Verifikasi pra-merge di Shreyas & HCBNJ; `deck_strict_types` dapat dilonggarkan tanpa rebuild |
| Jitter menurunkan presisi pola | Clamp batas peta; hanya titik peta; magnitudo configurable (0 = off) |
| Popup Another_device tidak hilang otomatis | Kalibrasi live menentukan; opsi tap-reload ditambahkan bila perlu |
| Mirror skenario kurang cocok utk sebagian basis | Pilihan acak setara antara versi asli & cermin; bisa dimatikan via config |
