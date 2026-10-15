# Aset Template — Sumber & Catatan

Folder ini berisi template PNG hasil potongan antarmuka Clash of Clans yang
diambil dari **Simplicity v3.50.0** (folder yang disediakan pengguna di
`D:\HH\coc bot\auto-farm-bot\Simplicity v3.50.0\Templates`), dipakai sebagai
referensi aset deteksi. Pendekatan deteksinya (grayscale + `cv2.matchTemplate`
TM_CCOEFF_NORMED pada layar penuh, threshold sekitar 0.5) terdokumentasi di
`attacks/attacks.py` milik Simplicity dan diimplementasikan ulang (kode sendiri)
di `coclab/cards.py`.

## Struktur

- `deck/` — kartu deck battle:
  `dragon.png`, `balloon.png`, `rage.png`, `freeze.png`, hero
  `queen/bk/warden/rc/prince`, `empty_siege.png`, `siege_with_troops.png`,
  `E_Drag.png`, `azure_dragon.png`, `ice_minion.png`, `ice_golem.png`,
  `event_goblin.png`.
  - `blimp_card.png`, `duke_card.png`, `extra_pink.png` = **crop buatan sendiri**
    dari screenshot akun pengguna (kartu yang tidak ada di set Simplicity:
    siege blimp, hero dragon "Duke", dan kartu pasukan ekstra).
- `ui/` — tombol & dialog: End Battle, Surrender (+window), Continue, Next,
  bintang hasil (1/2/3 star), tombol tutup panel, collector, dll.
- `train/` — isi folder Smart_Auto_train Simplicity: ikon grid pasukan/spell/
  siege (subfolder `Army Troops/`, `Spells/`, `Siege Machines/`, `s_troops/`,
  `to_train/`) + jendela dialog `army_window.png`,
  `use_army_recipe_window.png`, `remove_troops_window.png`, `trash_icon.png`,
  `use_button.png`, indikator `army_space_*` / `Spell_space_*`.
- `walls/` — level wall (untuk fitur upgrade wall).

## Catatan lisensi

- Semua gambar = potongan antarmuka game **Clash of Clans** (hak atas gambar:
  Supercell) untuk keperluan pengujian pribadi di akun sendiri, bukan
  distribusi ulang.
- Simplicity v3.50.0 dipakai sebagai sumber aset template; kode bot di repo ini
  tetap implementasi sendiri (`coclab/cards.py`) dengan atribusi pendekatan di
  docstring modul & catatan ini.
