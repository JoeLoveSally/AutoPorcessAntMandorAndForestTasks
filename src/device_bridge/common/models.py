from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Point:
    x: int
    y: int

    def tuple(self) -> tuple[int, int]:
        return (self.x, self.y)


@dataclass(frozen=True, slots=True)
class Size:
    width: int
    height: int

    def contains(self, point: tuple[int, int]) -> bool:
        x, y = point
        return 0 <= x < self.width and 0 <= y < self.height


@dataclass(frozen=True, slots=True)
class DeviceInfo:
    serial: str
    state: str
    details: str = ""


@dataclass(frozen=True, slots=True)
class DeviceMetrics:
    operation: str
    samples_ms: tuple[float, ...]

    @property
    def p50_ms(self) -> float:
        return _percentile(self.samples_ms, 0.50)

    @property
    def p95_ms(self) -> float:
        return _percentile(self.samples_ms, 0.95)


def _percentile(values: tuple[float, ...], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * ratio))
    return ordered[index]
