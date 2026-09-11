import time

from domain_data import AutomationError


class Budget:
    def __init__(self, seconds, parent=None):
        self.deadline = min(time.monotonic() + seconds, parent.deadline if parent else float("inf"))

    def check(self):
        if time.monotonic() >= self.deadline:
            raise AutomationError("Execution budget exhausted", "TIMEOUT")

    @property
    def remaining(self):
        return max(0, self.deadline - time.monotonic())
