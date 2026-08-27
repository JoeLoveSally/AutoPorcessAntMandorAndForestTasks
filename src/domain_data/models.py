from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


class Page(StrEnum):
    ALIPAY_HOME = "alipay_home"
    MANOR_HOME = "manor_home"
    MANOR_DIARY = "manor_diary"
    MANOR_FAMILY = "manor_family"
    MANOR_FAMILY_TASKS = "manor_family_tasks"
    MANOR_DONATION_PROJECTS = "manor_donation_projects"
    MANOR_DONATION_DETAIL = "manor_donation_detail"
    MANOR_DONATION_CONFIRM = "manor_donation_confirm"
    MANOR_DONATION_SUCCESS = "manor_donation_success"
    MANOR_FEED_TASKS = "manor_feed_tasks"
    MANOR_QUIZ = "manor_quiz"
    MANOR_QUIZ_RESULT = "manor_quiz_result"
    EXTERNAL_BROWSE = "external_browse"
    LOTTERY = "lottery"
    BABA_FARM = "baba_farm"
    BABA_FARM_TASKS = "baba_farm_tasks"
    BABA_FARM_HARVEST = "baba_farm_harvest"
    CHICKEN_KITCHEN = "chicken_kitchen"
    KITCHEN_DONATE = "kitchen_donate"
    FOREST_HOME = "forest_home"
    FOREST_SIGN_REWARD = "forest_sign_reward"
    FOREST_FRIEND = "forest_friend"
    FOREST_TREASURE = "forest_treasure"
    FOREST_LOTTERY = "forest_lottery"
    FOREST_LOVE_PLANT = "forest_love_plant"
    FOREST_CO_PLANT = "forest_co_plant"
    ENERGY_RAIN = "energy_rain"
    ENERGY_RAIN_GAME = "energy_rain_game"
    ENERGY_RAIN_GIFT = "energy_rain_gift"
    ENERGY_RAIN_RESULT = "energy_rain_result"
    UNKNOWN = "unknown"


class OverlayType(StrEnum):
    NONE = "none"
    LOADING = "loading"
    FEED_OVERFLOW = "feed_overflow"
    PRODUCT_QUIZ = "product_quiz"
    REWARD = "reward"
    CONFIRMATION = "confirmation"
    FOOD_SELECTION = "food_selection"
    PROMO = "promo"
    UNKNOWN = "unknown"


class StepStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    ALREADY_DONE = "already_done"
    NOT_AVAILABLE = "not_available"
    FAILED = "failed"


class ActionKind(StrEnum):
    TAP = "tap"
    SWIPE = "swipe"
    BACK = "back"
    WAIT = "wait"


class ActionStatus(StrEnum):
    EXECUTED = "executed"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class Bounds:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def valid(self) -> bool:
        return self.left >= 0 and self.top >= 0 and self.right > self.left and self.bottom > self.top

    @property
    def center(self) -> tuple[int, int]:
        return ((self.left + self.right) // 2, (self.top + self.bottom) // 2)

    def expanded(self, x: int, y: int) -> Bounds:
        return Bounds(max(0, self.left - x), max(0, self.top - y), self.right + x, self.bottom + y)


@dataclass(frozen=True, slots=True)
class Observation:
    id: str
    captured_at: datetime
    device_serial: str
    package: str | None
    activity: str | None
    width: int
    height: int
    screenshot_path: Path | None
    ui_tree_path: Path | None
    screenshot: bytes | None = field(default=None, repr=False)
    ui_tree: Any | None = field(default=None, repr=False)
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Element:
    key: str
    bounds: Bounds
    observation_id: str
    text: str | None = None
    clickable: bool = True
    enabled: bool = True
    source: str = "unknown"
    confidence: float = 1.0

    @property
    def center(self) -> tuple[int, int]:
        return self.bounds.center


@dataclass(frozen=True, slots=True)
class Overlay:
    type: OverlayType
    elements: dict[str, Element] = field(default_factory=dict)
    evidence: tuple[str, ...] = ()
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class DetectedScreen:
    page: Page
    observation: Observation
    elements: dict[str, Element] = field(default_factory=dict)
    overlays: tuple[Overlay, ...] = ()
    evidence: tuple[str, ...] = ()
    confidence: float = 0.0

    def element(self, key: str) -> Element | None:
        for overlay in reversed(self.overlays):
            if key in overlay.elements:
                return overlay.elements[key]
        return self.elements.get(key)


@dataclass(frozen=True, slots=True)
class Action:
    name: str
    kind: ActionKind
    element_key: str | None = None
    start: tuple[int, int] | None = None
    end: tuple[int, int] | None = None
    duration_ms: int = 400


@dataclass(frozen=True, slots=True)
class ActionResult:
    name: str
    status: ActionStatus
    before_observation_id: str
    after_observation_id: str | None = None
    point: tuple[int, int] | None = None
    error: str | None = None
    elapsed_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class StepResult:
    name: str
    status: StepStatus
    detail: str | None = None
    attempts: int = 1


@dataclass(slots=True)
class RunResult:
    run_id: str
    workflow: str
    status: StepStatus
    started_at: datetime
    finished_at: datetime | None = None
    steps: list[StepResult] = field(default_factory=list)
    actions: list[ActionResult] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        value["started_at"] = self.started_at.isoformat()
        value["finished_at"] = self.finished_at.isoformat() if self.finished_at else None
        for step in value["steps"]:
            step["status"] = step["status"].value
        for action in value["actions"]:
            action["status"] = action["status"].value
        return value
