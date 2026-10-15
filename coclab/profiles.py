"""Profile files for the GUI. Each profile = satu config bot penuh (JSON)."""

from __future__ import annotations

import json
from pathlib import Path

from coclab.paths import base_dir

PROFILES_DIR = base_dir() / "profiles"

# field yang bisa diedit cepat dari GUI (sisanya tetap ikut file)
EDITABLE_FIELDS = (
    "device_address",
    "min_gold",
    "min_elixir",
    "min_dark",
    "speed_up_taps",
    "end_delay_s",
    "threshold",
)


def ensure_dir(directory: Path = PROFILES_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def list_profiles(directory: Path = PROFILES_DIR) -> list[str]:
    ensure_dir(directory)
    return sorted(p.stem for p in directory.glob("*.json"))


def profile_path(name: str, directory: Path = PROFILES_DIR) -> Path:
    return ensure_dir(directory) / f"{name}.json"


def load_profile(name: str, directory: Path = PROFILES_DIR) -> dict:
    return json.loads(profile_path(name, directory).read_text(encoding="utf-8"))


def save_profile(name: str, data: dict, directory: Path = PROFILES_DIR) -> Path:
    path = profile_path(name, directory)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def create_from_template(name: str, template: Path, directory: Path = PROFILES_DIR) -> Path:
    data = json.loads(Path(template).read_text(encoding="utf-8"))
    return save_profile(name, data, directory)


def merge_missing(data: dict, template: dict) -> int:
    """Fill keys missing in `data` from `template`; returns how many were filled."""
    filled = 0
    for key, value in template.items():
        if key not in data:
            data[key] = value
            filled += 1
    return filled


def rename_profile(old: str, new: str, directory: Path = PROFILES_DIR) -> Path:
    """Ganti nama file profil (akun) dari `old` ke `new`."""
    old_path = profile_path(old, directory)
    new_path = profile_path(new, directory)
    if not old_path.is_file():
        raise FileNotFoundError(f"profil '{old}' tidak ada")
    if new_path.exists():
        raise FileExistsError(f"profil '{new}' sudah ada")
    old_path.rename(new_path)
    return new_path
