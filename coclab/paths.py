"""Folder dasar aplikasi: root repo saat dev, folder exe saat dibungkus PyInstaller."""

from __future__ import annotations

import sys
from pathlib import Path


def base_dir() -> Path:
    """Root data aplikasi (config, assets, profiles).

    - Dev (py gui.py)      : root folder repo
    - Frozen (GARUDA.exe)  : folder tempat exe berada (file data ada di samping exe)
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent
