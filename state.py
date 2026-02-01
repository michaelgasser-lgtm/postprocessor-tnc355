from __future__ import annotations
from dataclasses import dataclass

@dataclass
class State:
    tool_active: int | None = None
    x: float | None = None
    y: float | None = None
    z: float | None = None
