from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import time

from ..actions.executor import ActionExecutor
from ..device.adb import AndroidDevice
from ..domain.models import ActionResult, DetectedPage, PageType, RunResult, TaskResult, TaskStatus
from ..evidence.recorder import EvidenceRecorder, HumanRunLogger
from ..perception.detector import PageDetector
from ..perception.energy import detect_energy_balls
from ..perception.observation import ObservationCollector
from ..runtime.config import Config
from ..runtime.errors import AutomationError, TimeoutError
from ..runtime.wait import wait_until
from .lottery import LotteryRunner


class ForestDailyWorkflow:
    def __init__(self, device: AndroidDevice, config: Config):
        self.device = device
        self.config = config
        self.detector = PageDetector()
        self.recorder = EvidenceRecorder(config.runtime.artifacts_directory)
        self.observations = ObservationCollector(device)
        self.actions = ActionExecutor(device)
        self.run_directory: Path | None = None
        self.log: HumanRunLogger | None = None
        self._capture_index = 0

    @classmethod
    def create(cls, device: AndroidDevice, config: Config) -> "ForestDailyWorkflow":
        return cls(device, config)

    def run(self) -> RunResult:
        started = datetime.now(timezone.utc)
        result = RunResult("forest_daily", TaskStatus.UNKNOWN, started)
        self.run_directory = self.recorder.new_run()
        self.log = HumanRunLogger(self.config.runtime.logs_directory, started)
        result.evidence_directory = self.run_directory
        self._log("workflow.start", workflow=result.workflow, device=self.device.serial)
        try:
            self.device.launch_package(self.config.package)
            time.sleep(self.config.runtime.launch_wait_seconds)
            home = self._capture_page("alipay_home")
            if home.type is not PageType.ALIPAY_HOME:
                return self._finish(result, TaskStatus.UNKNOWN, "Alipay home not recognized")
            forest = self._tap_and_wait(
                result, home, "forest", "open_forest", PageType.FOREST_HOME, "forest_home"
            )
            lottery = self._collect_friend_energy(result, forest)
            forest = self._handle_forest_lotteries(result, lottery)
            forest = self._handle_energy_rain(result, forest)
            self._handle_co_plant(result, forest)
            return self._finish(result, TaskStatus.SUCCESS, "Forest energy, lotteries, rain and co-plant handled")
        except TimeoutError as exc:
            return self._finish(result, TaskStatus.UNKNOWN, str(exc))
        except AutomationError as exc:
            return self._finish(result, TaskStatus.FAILED, str(exc))
        except Exception as exc:
            return self._finish(result, TaskStatus.FAILED, str(exc))

    def _collect_friend_energy(self, result: RunResult, page: DetectedPage) -> DetectedPage:
        current = page
        taps = 0
        if "find_energy" in current.elements:
            action = self.actions.tap(current, "find_energy", "open_friend_energy")
            self._record_action(result, action)
            current = self._capture_page("friend_energy")
        for index in range(45):
            if current.type is PageType.LOTTERY:
                result.tasks.append(TaskResult("friend_energy", TaskStatus.SUCCESS, f"tapped {taps} energy bubble(s)"))
                return current
            if current.type is not PageType.FOREST_HOME:
                raise AutomationError(f"Unexpected page while collecting energy: {current.type.value}")
            keys = [key for key in current.elements if key.startswith("energy_")]
            for key in keys:
                action = self.actions.tap(current, key, f"collect_energy_{taps + 1}")
                self._record_action(result, action)
                if action.status.value == "executed":
                    taps += 1
            width, height = self.device.screen_size()
            self.device.swipe((width // 2, int(height * 0.76)), (width // 2, int(height * 0.30)), 450)
            self._log("forest.friend_list_swipe", index=index + 1, energy_taps=len(keys))
            current = self._capture_page("friend_energy_scan")
        raise TimeoutError("Forest friend collection did not reach the lottery")

    def _handle_forest_lotteries(self, result: RunResult, first: DetectedPage) -> DetectedPage:
        runner = LotteryRunner(self)
        current = first
        for index in range(2):
            task_key = "task_market" if "task_market" in current.elements else "missing_market"
            runner.run(result, current, task_key, f"forest_lottery_{index + 1}", 2)
            current = self._capture_page(f"forest_lottery_{index + 1}_settled")
            if index == 0:
                if "next_wheel" in current.elements:
                    current = self._tap_and_wait(
                        result, current, "next_wheel", "open_second_forest_lottery",
                        PageType.LOTTERY, "second_forest_lottery",
                    )
                    continue
                forest = self._return_to_forest(result, current, "leave_first_forest_lottery")
                if "lottery" not in forest.elements:
                    raise AutomationError("Second Forest lottery entry was not found")
                current = self._tap_and_wait(
                    result, forest, "lottery", "open_second_forest_lottery",
                    PageType.LOTTERY, "second_forest_lottery",
                )
        return self._return_to_forest(result, current, "leave_forest_lotteries")

    def _return_to_forest(self, result: RunResult, page: DetectedPage, name: str) -> DetectedPage:
        current = page
        for index in range(3):
            back = self.actions.back(current, f"{name}_{index + 1}")
            self._record_action(result, back)
            current = self._capture_page(f"{name}_after_{index + 1}")
            if current.type is PageType.FOREST_HOME:
                return current
            if current.type is not PageType.LOTTERY:
                raise AutomationError(f"Unexpected page while returning to Forest: {current.type.value}")
        raise TimeoutError("Unable to return to Forest home after lotteries")

    def _handle_energy_rain(self, result: RunResult, forest: DetectedPage) -> DetectedPage:
        if "energy_rain" not in forest.elements:
            result.tasks.append(TaskResult("energy_rain", TaskStatus.SKIPPED, "entry not visible"))
            return forest
        action = self.actions.tap(forest, "energy_rain", "open_energy_rain")
        self._record_action(result, action)
        rain = self._capture_page("energy_rain")
        if rain.type is not PageType.FOREST_RAIN or "start" not in rain.elements:
            raise AutomationError("Energy rain start page or start button was not recognized")
        start = self.actions.tap(rain, "start", "start_energy_rain_1")
        self._record_action(result, start)
        if start.status.value != "executed":
            raise AutomationError(start.error or "Unable to start first energy rain")
        first = self._play_energy_rain(1)
        result_page = self._wait_for_page(PageType.FOREST_RAIN_RESULT, "energy_rain_result_1")
        rounds = 1
        if "friend_xiaobu" in result_page.elements:
            gift = self.actions.tap(result_page, "friend_xiaobu", "gift_energy_rain_to_xiaobu")
            self._record_action(result, gift)
            if gift.status.value != "executed":
                raise AutomationError(gift.error or "Unable to gift energy rain to 小布")
        elif "more_friends" in result_page.elements:
            picker = self._tap_and_wait(
                result, result_page, "more_friends", "open_more_energy_rain_friends",
                PageType.FOREST_FRIEND_PICKER, "energy_rain_friend_picker",
            )
            self._choose_xiaobu(result, picker)
        else:
            raise AutomationError("Energy rain result has no 小布 or more-friends action")
        if "friend_xiaobu" in result_page.elements or "more_friends" in result_page.elements:
            next_page = self._capture_page("energy_rain_after_gift")
            if next_page.type is not PageType.FOREST_RAIN or "start" not in next_page.elements:
                raise AutomationError(f"Second energy rain did not open: {next_page.type.value}")
            again = self.actions.tap(next_page, "start", "start_energy_rain_2")
            self._record_action(result, again)
            if again.status.value != "executed":
                raise AutomationError(again.error or "Unable to start second energy rain")
            self._play_energy_rain(2)
            result_page = self._wait_for_page(PageType.FOREST_RAIN_RESULT, "energy_rain_result_2")
            rounds = 2
        result.tasks.append(TaskResult(
            "energy_rain", TaskStatus.SUCCESS, f"played {rounds} round(s), first round tapped {first} ball(s)"
        ))
        back = self.actions.back(result_page, "leave_energy_rain")
        self._record_action(result, back)
        return self._wait_for_page(PageType.FOREST_HOME, "forest_after_energy_rain")

    def _choose_xiaobu(self, result: RunResult, picker: DetectedPage) -> DetectedPage:
        current = picker
        if "friend_xiaobu" not in current.elements and "more_friends" in current.elements:
            action = self.actions.tap(current, "more_friends", "open_more_friends")
            self._record_action(result, action)
            current = self._wait_for_page(PageType.FOREST_FRIEND_PICKER, "more_friends")
        for index in range(12):
            if "friend_xiaobu" in current.elements:
                action = self.actions.tap(current, "friend_xiaobu", "select_xiaobu")
                self._record_action(result, action)
                after = self._capture_page("xiaobu_selected")
                if after.type is PageType.FOREST_FRIEND_PICKER and "confirm_gift" in after.elements:
                    confirm = self.actions.tap(after, "confirm_gift", "confirm_gift_xiaobu")
                    self._record_action(result, confirm)
                return after
            width, height = self.device.screen_size()
            self.device.swipe((width // 2, int(height * 0.78)), (width // 2, int(height * 0.35)), 450)
            current = self._capture_page(f"find_xiaobu_{index + 1}")
        raise AutomationError("Friend 小布 was not found after opening more friends")

    def _play_energy_rain(self, round_number: int) -> int:
        if self.run_directory is None:
            raise RuntimeError("workflow has not started")
        deadline = time.monotonic() + self.config.runtime.energy_rain_seconds
        taps = 0
        frames = 0
        while time.monotonic() < deadline:
            points = detect_energy_balls(self.device.screenshot_bytes())
            frames += 1
            if points:
                self.device.tap_many(points)
                taps += len(points)
        evidence = self.run_directory / f"energy-rain-{round_number}-final.png"
        self.device.screenshot(evidence)
        self._log("energy_rain.round_complete", round=round_number, frames=frames, taps=taps)
        return taps

    def _handle_co_plant(self, result: RunResult, forest: DetectedPage) -> None:
        if "co_plant" not in forest.elements:
            result.tasks.append(TaskResult("love_co_plant", TaskStatus.SKIPPED, "entry not visible"))
            return
        page = self._tap_and_wait(
            result, forest, "co_plant", "open_co_plant", PageType.FOREST_CO_PLANT,
            "co_plant", required_elements=("water",),
        )
        if "amount_100" in page.elements:
            amount = self.actions.tap(page, "amount_100", "select_100g")
            self._record_action(result, amount)
            page = self._wait_for_page(PageType.FOREST_CO_PLANT, "co_plant_100g", required_elements=("water",))
        water = self.actions.tap(page, "water", "water_love_co_plant")
        self._record_action(result, water)
        self._capture_page("co_plant_after_water")
        result.tasks.append(TaskResult("love_co_plant", TaskStatus.SUCCESS, "watered 100g"))

    def _tap_and_wait(self, result, page, key, action_name, expected, name, required_elements=()):
        action = self.actions.tap(page, key, action_name)
        self._record_action(result, action)
        if action.status.value != "executed":
            raise AutomationError(action.error or f"Action failed: {action_name}")
        return self._wait_for_page(expected, name, required_elements=required_elements)

    def _capture_page(self, name: str) -> DetectedPage:
        if self.run_directory is None:
            raise RuntimeError("workflow has not started")
        self._capture_index += 1
        stem = f"{self._capture_index:03d}-{name}"
        observation = self.observations.observe(self.run_directory, stem)
        self.recorder.write_observation_metadata(self.run_directory, observation, stem)
        page = self.detector.detect(observation)
        self._log("observation.captured", name=name, page=page.type.value,
                  elements=sorted(page.elements), errors=list(observation.errors))
        return page

    def _wait_for_page(self, expected, name, required_elements=(), required_any_elements=()):
        latest = None
        def observe():
            nonlocal latest
            latest = self._capture_page(name)
            return latest.observation
        def matches(_):
            return latest is not None and latest.type is expected and all(
                key in latest.elements for key in required_elements
            ) and (not required_any_elements or any(key in latest.elements for key in required_any_elements))
        wait_until(observe, matches, self.config.runtime.page_timeout_seconds,
                   self.config.runtime.poll_interval_seconds)
        return latest

    def _record_action(self, result: RunResult, action: ActionResult) -> None:
        result.actions.append(action)
        self._log("action.completed", action=action.name, status=action.status.value,
                  point=action.point, error=action.error)

    def _finish(self, result: RunResult, status: TaskStatus, detail: str | None) -> RunResult:
        result.status = status
        result.finished_at = datetime.now(timezone.utc)
        if detail and status in {TaskStatus.UNKNOWN, TaskStatus.FAILED}:
            result.error = {"type": status.value, "message": detail}
        result.tasks.append(TaskResult("forest_daily", status, detail))
        self._log("workflow.finish", status=status.value, detail=detail)
        if self.run_directory is not None:
            self.recorder.write_result(self.run_directory, result)
        return result

    def _log(self, event: str, **fields) -> None:
        if self.log is not None:
            self.log.info(event, **fields)
