from __future__ import annotations

from collections.abc import Callable
import time

from ..domain.models import Observation
from .errors import TimeoutError


def wait_until(
    observe: Callable[[], Observation],
    predicate: Callable[[Observation], bool],
    timeout_seconds: float,
    interval_seconds: float,
) -> Observation:
    if timeout_seconds <= 0 or interval_seconds <= 0:
        raise ValueError("timeout and interval must be positive")
    deadline = time.monotonic() + timeout_seconds
    while True:
        current = observe()
        if predicate(current):
            return current
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"condition not met within {timeout_seconds:g}s")
        time.sleep(min(interval_seconds, remaining))
