from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum


class AutomationError(RuntimeError):
    def __init__(self, message: str, code: str = "FAILED"):
        super().__init__(message)
        self.code = code


class Probe(StrEnum):
    READY = "READY"
    ALREADY_DONE = "ALREADY_DONE"
    NOT_VISIBLE = "NOT_VISIBLE"
    NOT_PRESENT_CONFIRMED = "NOT_PRESENT_CONFIRMED"
    UNKNOWN = "UNKNOWN"
    RESULT_UNKNOWN = "RESULT_UNKNOWN"


@dataclass(frozen=True)
class Element:
    text: str
    bounds: tuple[int, int, int, int]
    observation: str
    source: str = "ocr"
    score: float = 1.0

    @property
    def point(self):
        x1, y1, x2, y2 = self.bounds
        return ((x1 + x2) // 2, (y1 + y2) // 2)


@dataclass
class Observation:
    id: str
    captured: float
    width: int
    height: int
    package: str
    elements: list[Element]
    page: str = "UNKNOWN"
    overlays: list[str] = field(default_factory=list)
    image: object = None

    def find(self, pattern: str, region=(0.0, 0.0, 1.0, 1.0)) -> list[Element]:
        left, top, right, bottom = region
        return [e for e in self.elements if re.search(pattern, e.text)
                and left <= e.point[0] / self.width <= right
                and top <= e.point[1] / self.height <= bottom]

    def has(self, pattern: str, region=(0.0, 0.0, 1.0, 1.0)) -> bool:
        return bool(self.find(pattern, region))

    def one(self, pattern: str, region=(0.0, 0.0, 1.0, 1.0)) -> Element:
        matches = self.find(pattern, region)
        if len(matches) != 1:
            raise AutomationError(f"Expected unique target {pattern}: found {len(matches)}", "AMBIGUOUS")
        return matches[0]
