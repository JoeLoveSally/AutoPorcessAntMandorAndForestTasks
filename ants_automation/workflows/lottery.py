from __future__ import annotations

import time

from ..domain.models import PageType, TaskResult, TaskStatus
from ..runtime.errors import AutomationError, TimeoutError


class LotteryRunner:
    """Runs only explicitly allow-listed browse tasks, then consumes every draw."""

    def __init__(self, workflow):
        self.workflow = workflow

    def run(self, result, page, task_key: str, name: str, max_tasks: int) -> None:
        completed = 0
        current = page
        while task_key in current.elements and completed < max_tasks:
            action = self.workflow.actions.tap(
                current, task_key, f"{name}_task_{completed + 1}"
            )
            self.workflow._record_action(result, action)
            if action.status.value != "executed":
                raise AutomationError(action.error or f"Unable to start {name} task")
            self._wait_external_and_return(result, current, name, completed + 1)
            current = self.workflow._wait_for_page(PageType.LOTTERY, f"{name}_after_task")
            completed += 1

        if task_key in current.elements:
            raise AutomationError(f"{name} task limit reached before completion")

        draws = 0
        while "draw" in current.elements and draws < 12:
            action = self.workflow.actions.tap(current, "draw", f"{name}_draw_{draws + 1}")
            self.workflow._record_action(result, action)
            if action.status.value != "executed":
                raise AutomationError(action.error or f"Unable to draw {name}")
            reward = self.workflow._wait_for_page(
                PageType.LOTTERY_REWARD, f"{name}_reward_{draws + 1}",
                required_elements=("confirm_reward",),
            )
            confirm = self.workflow.actions.tap(
                reward, "confirm_reward", f"{name}_confirm_{draws + 1}"
            )
            self.workflow._record_action(result, confirm)
            if confirm.status.value != "executed":
                raise AutomationError(confirm.error or f"Unable to confirm {name} reward")
            current = self.workflow._wait_for_page(PageType.LOTTERY, f"{name}_after_draw")
            draws += 1
        if "draw" in current.elements:
            raise AutomationError(f"{name} draw limit reached before all chances were consumed")
        if draws == 0 and "draws_done" not in current.elements:
            raise AutomationError(f"{name} has neither an available draw nor a completed state")
        result.tasks.append(
            TaskResult(name, TaskStatus.SUCCESS, f"completed {completed} task(s), drew {draws} time(s)")
        )

    def _wait_external_and_return(self, result, source_page, name: str, index: int) -> None:
        deadline = time.monotonic() + self.workflow.config.runtime.external_task_timeout_seconds
        next_swipe = time.monotonic() + self.workflow.config.runtime.external_swipe_interval_seconds
        latest = None
        while time.monotonic() < deadline:
            latest = self.workflow._capture_page(f"{name}_external_{index}")
            if latest.type is PageType.MANOR_FEED_VIDEO_COMPLETE:
                back = self.workflow.actions.back(latest, f"{name}_return_{index}")
                self.workflow._record_action(result, back)
                if back.status.value != "executed":
                    raise AutomationError(back.error or "Unable to leave completed external task")
                return
            if time.monotonic() >= next_swipe:
                width, height = self.workflow.device.screen_size()
                self.workflow.device.swipe(
                    (width // 2, int(height * 0.72)),
                    (width // 2, int(height * 0.42)),
                    500,
                )
                self.workflow._log("external_task.swipe", task=name, index=index)
                next_swipe = time.monotonic() + self.workflow.config.runtime.external_swipe_interval_seconds
            time.sleep(self.workflow.config.runtime.poll_interval_seconds)
        raise TimeoutError(f"Timed out waiting for {name} external task completion")
