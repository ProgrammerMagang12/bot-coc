"""Bot state definitions and step results."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BotState(Enum):
    CONNECT = "CONNECT"
    PREPARE = "PREPARE"
    FIND_ATTACK = "FIND_ATTACK"
    MATCHMAKING = "MATCHMAKING"
    LOOT_CHECK = "LOOT_CHECK"
    ATTACK = "ATTACK"
    RETURN_HOME = "RETURN_HOME"
    DONE = "DONE"


@dataclass
class StepResult:
    ok: bool
    reason: str = ""
    data: dict | None = None
