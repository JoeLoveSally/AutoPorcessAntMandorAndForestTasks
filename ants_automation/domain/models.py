from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class PageType(str, Enum):
    ALIPAY_HOME = "ALIPAY_HOME"
    MANOR_HOME = "MANOR_HOME"
    MANOR_FAMILY = "MANOR_FAMILY"
    MANOR_DONATION = "MANOR_DONATION"
    FOREST_HOME = "FOREST_HOME"
    UNKNOWN = "UNKNOWN"


class TaskStatus(str, Enum):
    SUCCESS = "success"
    ALREADY_DONE = "already_done"
    SKIPPED = "skipped"
    UNKNOWN = "unknown"
    FAILED = "failed"


class ActionStatus(str, Enum):
    EXECUTED = "executed"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass(frozen=True)
class Bounds:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def valid(self) -> bool:
        return self.right > self.left and self.bottom > self.top

    @property
    def center(self) -> tuple[int, int]:
        return ((self.left + self.right) // 2, (self.top + self.bottom) // 2)

    def contains(self, point: tuple[int, int]) -> bool:
        x, y = point
        return self.left <= x < self.right and self.top <= y < self.bottom


@dataclass(frozen=True)
class Observation:
    timestamp: datetime
    device_serial: str | None
    package: str | None
    activity: str | None
    screenshot_path: Path | None
    ui_tree_path: Path | None
    ui_tree: Any | None
    visible_labels: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class UIElement:
    key: str
    text: str | None
    bounds: Bounds
    clickable: bool
    enabled: bool
    source: str
    observation_timestamp: datetime

    @property
    def center(self) -> tuple[int, int]:
        return self.bounds.center


@dataclass(frozen=True)
class DetectedPage:
    type: PageType
    observation: Observation
    elements: dict[str, UIElement] = field(default_factory=dict)
    evidence: tuple[str, ...] = ()
    confidence: float = 0.0


@dataclass(frozen=True)
class TaskSpec:
    name: str
    entry_page: PageType
    preconditions: tuple[str, ...]
    action: str
    success_conditions: tuple[str, ...]
    already_done_conditions: tuple[str, ...]
    unknown_conditions: tuple[str, ...]


@dataclass(frozen=True)
class ActionResult:
    name: str
    status: ActionStatus
    point: tuple[int, int] | None = None
    error: str | None = None


@dataclass(frozen=True)
class TaskResult:
    name: str
    status: TaskStatus
    detail: str | None = None


@dataclass
class RunResult:
    workflow: str
    status: TaskStatus
    started_at: datetime
    finished_at: datetime | None = None
    tasks: list[TaskResult] = field(default_factory=list)
    actions: list[ActionResult] = field(default_factory=list)
    error: dict[str, str] | None = None
    evidence_directory: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        value["started_at"] = self.started_at.isoformat()
        value["finished_at"] = self.finished_at.isoformat() if self.finished_at else None
        value["evidence_directory"] = (
            str(self.evidence_directory) if self.evidence_directory else None
        )
        for item in value["tasks"]:
            item["status"] = item["status"].value
        for item in value["actions"]:
            item["status"] = item["status"].value
        return value
