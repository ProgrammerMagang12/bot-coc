"""Thin ADB wrapper built on an injectable command runner."""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)

Runner = Callable[[list[str]], tuple[int, bytes, str]]


class AdbError(Exception):
    """Raised when an adb command fails or its result cannot be used."""


def _default_runner(args: list[str]) -> tuple[int, bytes, str]:
    completed = subprocess.run(
        args,
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return completed.returncode, completed.stdout, completed.stderr.decode("utf-8", "replace")


class Adb:
    def __init__(self, adb_path: str, runner: Runner | None = None) -> None:
        self.adb_path = adb_path
        self._runner = runner or _default_runner

    def _run(self, args: list[str]) -> bytes:
        try:
            rc, out, err = self._runner(args)
        except FileNotFoundError as exc:
            raise AdbError(f"adb executable not found: {self.adb_path}") from exc
        if rc != 0:
            raise AdbError(
                f"adb command failed (rc={rc}): {' '.join(args)}: {err.strip()[:200]}"
            )
        return out

    def shell(self, device: str, command: str) -> str:
        """Run `adb -s <device> shell <command>` and return stdout text."""
        out = self._run([self.adb_path, "-s", device, "shell", *command.split()])
        return out.decode("utf-8", "replace")

    def devices(self) -> list[str]:
        """Online serials from `adb devices`."""
        out = self._run([self.adb_path, "devices"])
        serials: list[str] = []
        for line in out.decode("utf-8", "replace").splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                serials.append(parts[0])
        return serials

    def connect(self, addr: str) -> str:
        """Run `adb connect <addr>` and return the resolved online serial."""
        self._run([self.adb_path, "connect", addr])
        for serial in self.devices():
            if serial == addr or serial.startswith(addr + ":"):
                return serial
        raise AdbError(
            f"device {addr} not online after connect (not listed by 'adb devices')"
        )

    def _ensure_online(self, device: str) -> None:
        if device not in self.devices():
            raise AdbError(f"device {device} not online (not listed by 'adb devices')")

    def wm_size(self, device: str) -> tuple[int, int]:
        """Parse `wm size` output; override > physical > generic > 1600x900 fallback."""
        self._ensure_online(device)
        out = self._run([self.adb_path, "-s", device, "shell", "wm size"]).decode(
            "utf-8", "replace"
        )
        for pattern in (
            r"Override size:\s*(\d+)x(\d+)",
            r"Physical size:\s*(\d+)x(\d+)",
            r"(\d+)\s*x\s*(\d+)",
        ):
            match = re.search(pattern, out, re.IGNORECASE)
            if match:
                width, height = int(match.group(1)), int(match.group(2))
                if width > 0 and height > 0:
                    return width, height
        logger.warning("could not parse 'wm size' output; falling back to 1600x900")
        return 1600, 900

    def tap(self, device: str, x: int, y: int) -> None:
        self._ensure_online(device)
        self._run(
            [self.adb_path, "-s", device, "shell", "input", "tap", str(x), str(y)]
        )

    def screencap(self, device: str, dest: str | Path) -> None:
        """Capture the screen straight to bytes via `exec-out screencap -p`."""
        self._ensure_online(device)
        data = self._run([self.adb_path, "-s", device, "exec-out", "screencap", "-p"])
        dest_path = Path(dest)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_bytes(data)

    def swipe(
        self,
        device: str,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: int = 300,
    ) -> None:
        """Touch-drag from (x1, y1) to (x2, y2); used for drag-to-deploy."""
        self._ensure_online(device)
        self._run(
            [
                self.adb_path,
                "-s",
                device,
                "shell",
                "input",
                "swipe",
                str(x1),
                str(y1),
                str(x2),
                str(y2),
                str(duration_ms),
            ]
        )
