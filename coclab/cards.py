"""Deteksi posisi kartu deck battle via template matching.

Pendekatan diadaptasi dari engine serangan Simplicity v3.50.0
(attacks/attacks.py): konversi grayscale + ``cv2.matchTemplate``
(TM_CCOEFF_NORMED) pada layar penuh, threshold sekitar 0.5, tanpa filter
region. Template PNG berasal dari folder Templates Simplicity — lihat
``assets/simplicity/NOTICE.md`` untuk sumber & catatan lisensi.

Modul ini murni fungsi gambar (tanpa ADB): input citra BGR/gray, output
``{nama_logis: (cx, cy, skor)}`` dalam koordinat piksel layar.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 0.55

# nama logis -> nama file template (relatif ke folder template deck)
CARD_FILES: dict[str, str] = {
    "dragon": "dragon.png",
    "balloon": "balloon.png",
    "rage": "rage.png",
    "freeze": "freeze.png",
    "hero_queen": "queen.png",
    "hero_bk": "bk.png",
    "hero_warden": "warden.png",
    "hero_rc": "rc.png",
    "hero_prince": "prince.png",
    "hero_duke": "duke_card.png",
    "siege_blimp": "blimp_card.png",
    "siege_empty": "empty_siege.png",
    "siege_loaded": "siege_with_troops.png",
    "extra_pink": "extra_pink.png",
}

HERO_KEYS: tuple[str, ...] = (
    "hero_queen",
    "hero_bk",
    "hero_warden",
    "hero_rc",
    "hero_prince",
    "hero_duke",
)

SIEGE_KEYS: tuple[str, ...] = ("siege_blimp", "siege_empty", "siege_loaded")

# tipe strict yang dikenali gate deck; di luar ini dicatat sebagai "ignored"
STRICT_KNOWN: set[str] = {"dragon", "balloon", "extra", "rage", "freeze"}

# tipe strict -> kunci pasukan yang menentukan apakah spell dikomposisikan
_ZERO_SKIP_SPELLS: dict[str, str] = {"rage": "rage_spell", "freeze": "freeze_spell"}


_tpl_cache: dict[str, np.ndarray | None] = {}


def _load_template(path: Path) -> np.ndarray | None:
    key = str(path)
    if key not in _tpl_cache:
        image = cv2.imread(key, cv2.IMREAD_GRAYSCALE)
        _tpl_cache[key] = image if image is not None and image.size > 0 else None
    return _tpl_cache[key]


def _to_gray(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return img
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def _slice_roi(
    img: np.ndarray, roi: list[float] | None
) -> tuple[np.ndarray, int, int]:
    if roi is None:
        return img, 0, 0
    height, width = img.shape[:2]
    x1 = max(0, int(roi[0] * width))
    y1 = max(0, int(roi[1] * height))
    x2 = min(width, int(roi[2] * width))
    y2 = min(height, int(roi[3] * height))
    return img[y1:y2, x1:x2], x1, y1


def detect_cards(
    img: np.ndarray,
    templates_dir: str | Path,
    names: list[str] | tuple[str, ...] | None = None,
    files: dict[str, str] | None = None,
    threshold: float = DEFAULT_THRESHOLD,
    roi: list[float] | None = None,
) -> dict[str, tuple[int, int, float]]:
    """Cari kartu pada citra.

    Kembalikan ``{nama: (cx, cy, skor)}`` hanya untuk kecocokan >= threshold.
    ``files`` menimpa peta nama->file (untuk pengujian); ``names`` membatasi
    kartu yang dicari; ``roi`` = [x1, y1, x2, y2] persen opsional.
    """
    mapping = dict(CARD_FILES if files is None else files)
    if names is not None:
        wanted = set(names)
        mapping = {name: mapping[name] for name in mapping if name in wanted}
    tpl_dir = Path(templates_dir)
    gray = _to_gray(img)
    crop, offset_x, offset_y = _slice_roi(gray, roi)
    if crop.size == 0:
        return {}
    results: dict[str, tuple[int, int, float]] = {}
    for name, filename in mapping.items():
        tpl = _load_template(tpl_dir / filename)
        if tpl is None:
            logger.debug("Template kartu hilang: %s", tpl_dir / filename)
            continue
        if tpl.shape[0] > crop.shape[0] or tpl.shape[1] > crop.shape[1]:
            continue
        try:
            res = cv2.matchTemplate(crop, tpl, cv2.TM_CCOEFF_NORMED)
        except cv2.error as exc:
            logger.warning("matchTemplate gagal untuk %s: %s", name, exc)
            continue
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        score = float(max_val) if max_val == max_val else 0.0  # penjaga NaN
        if score >= threshold:
            cx = max_loc[0] + tpl.shape[1] // 2 + offset_x
            cy = max_loc[1] + tpl.shape[0] // 2 + offset_y
            results[name] = (int(cx), int(cy), score)
    return results


def available_keys(templates_dir: str | Path) -> set[str]:
    """Kunci kartu yang file templatenya benar-benar ada di folder."""
    directory = Path(templates_dir)
    return {name for name, filename in CARD_FILES.items() if (directory / filename).is_file()}


def count_roi(cx: int, cy: int) -> tuple[int, int, int, int]:
    """Kotak badge jumlah di sekitar pusat kartu: (x1, y1, x2, y2)."""
    return (cx - 42, cy - 74, cx + 42, cy - 44)


@dataclass
class DeckCheck:
    """Hasil verifikasi deck: apakah gate boleh lanjut, dan alasannya."""

    ok: bool
    problems: list[str]
    soft_missing: list[str]
    notes: dict


def verify_deck(
    detected: dict[str, tuple[int, int, float]],
    army: dict[str, int],
    strict_types: list[str],
    extra_template: str | None = None,
    available: set[str] | None = None,
) -> DeckCheck:
    """Periksa tipe strict terdeteksi pada ``detected``.

    Urutan ``strict_types`` dipertahankan, duplikat di-skip. Tipe tak dikenal
    masuk ``notes["ignored"]``. ``extra`` tanpa ``extra_template`` dan spell
    rage/freeze dengan komposisi 0 bersifat opsional. Bila ``available``
    diberikan, tipe tanpa template dianggap soft-missing. Tipe wajib yang
    hilang masuk ``problems``; ``ok`` benar bila tidak ada masalah.
    """
    problems: list[str] = []
    soft_missing: list[str] = []
    notes: dict = {"ignored": [], "ok": []}
    seen: set[str] = set()
    for tipe in strict_types:
        if tipe in seen:
            continue
        seen.add(tipe)
        if tipe not in STRICT_KNOWN:
            notes["ignored"] += [tipe]
            continue
        if tipe == "extra":
            if extra_template is None:
                soft_missing += ["extra"]
                continue
            kunci = extra_template
        elif tipe in _ZERO_SKIP_SPELLS and army.get(_ZERO_SKIP_SPELLS[tipe], 0) == 0:
            continue
        else:
            kunci = tipe
        if available is not None and kunci not in available:
            soft_missing += [tipe]
            continue
        if kunci in detected:
            notes["ok"] += [tipe]
        else:
            problems += [tipe]
    return DeckCheck(
        ok=not problems,
        problems=problems,
        soft_missing=soft_missing,
        notes=notes,
    )
