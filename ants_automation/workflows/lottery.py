from __future__ import annotations

import time

from ..domain.models import PageType, TaskResult, TaskStatus
from ..runtime.errors import AutomationError, TimeoutError


class LotteryRunner:
    """Runs only explicitly allow-listed browse tasks, then consumes every draw."""

    def __init__(self, workflow):
        self.workflow = workflow

    def run(
        self, result, page, task_key: str, name: str, max_tasks: int,
        *, exchange_feed: bool = False,
    ) -> None:
        completed = 0
        current = page
        claim_key = f"claim_{task_key}"

        if exchange_feed and "exchange_feed" in current.elements:
            current = self._tap_and_settle(
                result, current, "exchange_feed", f"{name}_exchange_feed",
                required="confirm_exchange",
            )
            current = self._tap_and_settle(
                result, current, "confirm_exchange", f"{name}_confirm_exchange",
                forbidden="confirm_exchange",
            )

        if "claim_daily_chance" in current.elements:
            current = self._tap_and_settle(
                result, current, "claim_daily_chance", f"{name}_claim_daily",
                forbidden="claim_daily_chance",
            )

        if claim_key in current.elements:
            current = self._tap_and_settle(
                result, current, claim_key, f"{name}_claim_pending_task",
                forbidden=claim_key,
            )

        while task_key in current.elements and completed < max_tasks:
            action = self.workflow.actions.tap(
                current, task_key, f"{name}_task_{completed + 1}"
            )
            self.workflow._record_action(result, action)
            if action.status.value != "executed":
                raise AutomationError(action.error or f"Unable to start {name} task")
            self._wait_external_and_return(result, current, name, completed + 1)
            current = self.workflow._wait_for_page(
                PageType.LOTTERY, f"{name}_after_task",
                required_elements=(claim_key,),
            )
            current = self._tap_and_settle(
                result, current, claim_key, f"{name}_claim_task_{completed + 1}",
                forbidden=claim_key,
            )
            completed += 1

        if task_key in current.elements:
            raise AutomationError(f"{name} task limit reached before completion")

        draws = 0
        if "draw" in current.elements:
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
        if draws == 0 and "draws_done" not in current.elements:
            raise AutomationError(f"{name} has neither an available draw nor a completed state")
        result.tasks.append(
            TaskResult(name, TaskStatus.SUCCESS, f"completed {completed} task(s), drew {draws} time(s)")
        )

    def _tap_and_settle(
        self, result, page, key: str, action_name: str,
        *, required: str | None = None, forbidden: str | None = None,
    ):
        action = self.workflow.actions.tap(page, key, action_name)
        self.workflow._record_action(result, action)
        if action.status.value != "executed":
            raise AutomationError(action.error or f"Unable to {action_name}")
        deadline = time.monotonic() + self.workflow.config.runtime.page_timeout_seconds
        latest = None
        while time.monotonic() < deadline:
            latest = self.workflow._capture_page(f"{action_name}_after")
            if latest.type is PageType.LOTTERY:
                if required is not None and required not in latest.elements:
                    continue
                if forbidden is not None and forbidden in latest.elements:
                    continue
                return latest
            time.sleep(self.workflow.config.runtime.poll_interval_seconds)
        raise TimeoutError(f"Timed out waiting for {action_name} to settle")

    def _wait_external_and_return(self, result, source_page, name: str, index: int) -> None:
        deadline = time.monotonic() + max(
            self.workflow.config.runtime.external_task_timeout_seconds, 120.0
        )
        latest = None
        while time.monotonic() < deadline:
            latest = self.workflow._capture_page(f"{name}_external_{index}")
            if latest.type is PageType.EXTERNAL_TASK_COMPLETE:
                if "abandon_reward" in latest.elements:
                    abandon = self.workflow.actions.tap(
                        latest, "abandon_reward", f"{name}_abandon_reward_{index}"
                    )
                    self.workflow._record_action(result, abandon)
                    if abandon.status.value != "executed":
                        raise AutomationError(abandon.error or "Unable to dismiss reward popup")
                    time.sleep(self.workflow.config.runtime.poll_interval_seconds)
                    continue
                if "browse_complete" in latest.elements:
                    back = self.workflow.actions.back(latest, f"{name}_return_{index}")
                    self.workflow._record_action(result, back)
                    if back.status.value != "executed":
                        raise AutomationError(back.error or "Unable to leave completed browse task")
                    return
            if latest.type is PageType.MANOR_FEED_VIDEO_COMPLETE:
                back = self.workflow.actions.back(latest, f"{name}_return_{index}")
                self.workflow._record_action(result, back)
                if back.status.value != "executed":
                    raise AutomationError(back.error or "Unable to leave completed external task")
                return
            width, height = self.workflow.device.screen_size()
            # Capturing WebView UI on this device takes longer than the task's
            # idle timeout. Keep interacting for a full countdown window before
            # performing the next expensive observation.
            for swipe_index in range(8):
                if swipe_index == 4:
                    start_y, end_y = int(height * 0.42), int(height * 0.62)
                else:
                    start_y, end_y = int(height * 0.68), int(height * 0.48)
                self.workflow.device.swipe(
                    (width // 2, start_y),
                    (width // 2, end_y),
                    350,
                )
                self.workflow._log(
                    "external_task.swipe", task=name, index=index,
                    burst_position=swipe_index + 1,
                )
                time.sleep(1.25)
        raise TimeoutError(f"Timed out waiting for {name} external task completion")
