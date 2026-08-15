from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import time

from ..actions.executor import ActionExecutor
from ..device.adb import AndroidDevice
from ..domain.models import ActionResult, DetectedPage, PageType, RunResult, TaskResult, TaskStatus
from ..evidence.recorder import EvidenceRecorder, HumanRunLogger
from ..perception.detector import PageDetector
from ..perception.observation import ObservationCollector
from ..runtime.config import Config
from ..runtime.errors import AutomationError, TimeoutError
from ..runtime.wait import wait_until
from ..services.quiz_solver import WebQuizSolver
from .lottery import LotteryRunner


@dataclass
class ManorDailyWorkflow:
    device: AndroidDevice
    config: Config
    detector: PageDetector
    recorder: EvidenceRecorder

    def __post_init__(self) -> None:
        self.observations = ObservationCollector(self.device)
        self.actions = ActionExecutor(self.device)
        self.run_directory: Path | None = None
        self.log: HumanRunLogger | None = None
        self._capture_index = 0

    @classmethod
    def create(cls, device: AndroidDevice, config: Config) -> "ManorDailyWorkflow":
        return cls(device, config, PageDetector(), EvidenceRecorder(config.runtime.artifacts_directory))

    def run(self) -> RunResult:
        started = datetime.now(timezone.utc)
        result = RunResult("manor_daily", TaskStatus.UNKNOWN, started)
        self.run_directory = self.recorder.new_run()
        self.log = HumanRunLogger(self.config.runtime.logs_directory, started)
        result.evidence_directory = self.run_directory
        self._log("workflow.start", workflow=result.workflow, device=self.device.serial)
        try:
            self._log("app.launch", package=self.config.package)
            self.device.launch_package(self.config.package)
            time.sleep(self.config.runtime.launch_wait_seconds)
            home = self._capture_page("alipay_home")
            if home.type is not PageType.ALIPAY_HOME:
                return self._finish(result, TaskStatus.UNKNOWN, "Alipay home not recognized")

            manor_action = self.actions.tap(home, "manor", "open_manor")
            self._record_action(result, manor_action)
            if manor_action.status.value != "executed":
                return self._finish(result, TaskStatus.FAILED, manor_action.error)
            manor = self._wait_for_page(
                PageType.MANOR_HOME,
                "manor_home",
                required_elements=("family",),
            )
            if "diary" in manor.elements:
                diary_action = self.actions.tap(manor, "diary", "open_diary")
                self._record_action(result, diary_action)
                if diary_action.status.value != "executed":
                    return self._finish(result, TaskStatus.FAILED, diary_action.error)
                time.sleep(self.config.runtime.poll_interval_seconds)
                diary_after = self._capture_page("diary_after")
                result.tasks.append(
                    TaskResult("open_diary", TaskStatus.SUCCESS, "red-dot diary opened")
                )
                back = self.actions.back(manor, "leave_diary")
                self._record_action(result, back)
                if back.status.value != "executed":
                    return self._finish(result, TaskStatus.FAILED, back.error)
                manor = self._wait_for_page(PageType.MANOR_HOME, "manor_after_diary")
            else:
                result.tasks.append(TaskResult("open_diary", TaskStatus.SKIPPED, "no red-dot diary"))
            manor = self._handle_feed_rewards(result, manor)
            manor = self._handle_family_feeding(result, manor)

            family = manor.elements.get("family")
            if family is None:
                return self._finish(
                    result,
                    TaskStatus.UNKNOWN,
                    "MANOR_HOME has no registered Family element; collect visual evidence before adding a locator",
                )
            family_action = self.actions.tap(manor, "family", "open_family")
            self._record_action(result, family_action)
            if family_action.status.value != "executed":
                return self._finish(result, TaskStatus.FAILED, family_action.error)
            family_page = self._wait_for_page(
                PageType.MANOR_FAMILY,
                "family",
                required_any_elements=("sign_in", "signed"),
            )

            if "signed" in family_page.elements:
                result.tasks.append(
                    TaskResult("family_sign_in", TaskStatus.ALREADY_DONE, "already signed today")
                )
                open_tasks = self.actions.tap(family_page, "signed", "open_family_tasks")
                self._record_action(result, open_tasks)
                if open_tasks.status.value != "executed":
                    return self._finish(result, TaskStatus.FAILED, open_tasks.error)
                family_tasks = self._wait_for_family_tasks("family_tasks")
                sign_status = TaskStatus.ALREADY_DONE
            else:
                sign_action = self.actions.tap(family_page, "sign_in", "sign_in")
                self._record_action(result, sign_action)
                if sign_action.status.value != "executed":
                    return self._finish(result, TaskStatus.FAILED, sign_action.error)
                family_tasks = self._wait_for_family_tasks("sign_in_after")
                result.tasks.append(
                    TaskResult(
                        "family_sign_in",
                        TaskStatus.SUCCESS,
                        "task panel opened and sign-in control disappeared",
                    )
                )
                sign_status = TaskStatus.SUCCESS

            donation_status = self._handle_family_donation(result, family_tasks)
            manor = self._capture_page("manor_after_family")
            if manor.type is not PageType.MANOR_HOME:
                return self._finish(result, TaskStatus.UNKNOWN, "Did not return to Manor after family")
            self._handle_feed_tasks(result, manor)
            final_status = (
                TaskStatus.SUCCESS
                if TaskStatus.SUCCESS in {sign_status, donation_status}
                else TaskStatus.ALREADY_DONE
            )
            return self._finish(result, final_status, "Manor family, feed tasks and lotteries handled")
        except TimeoutError as exc:
            return self._finish(result, TaskStatus.UNKNOWN, str(exc))
        except AutomationError as exc:
            return self._finish(result, TaskStatus.FAILED, str(exc))
        except Exception as exc:
            return self._finish(result, TaskStatus.FAILED, str(exc))

    def _handle_feed_rewards(
        self,
        result: RunResult,
        page: DetectedPage,
        limit: int = 10,
    ) -> DetectedPage:
        rewarded = 0
        current = page
        while True:
            if "reward" not in current.elements:
                if rewarded == 0:
                    break
                next_reward = self._wait_for_optional_element(
                    PageType.MANOR_HOME,
                    "reward",
                    "reward_feed_quiet_wait",
                    timeout_seconds=min(2.0, self.config.runtime.page_timeout_seconds),
                    required_elements=("family",),
                )
                if next_reward is None:
                    break
                current = next_reward
            if rewarded >= limit:
                raise AutomationError(f"Feed reward limit reached: {limit}")
            action = self.actions.tap(current, "reward", f"reward_feed_{rewarded + 1}")
            self._record_action(result, action)
            if action.status.value != "executed":
                raise AutomationError(action.error or "Unable to reward feed helper")
            rewarded += 1
            time.sleep(self.config.runtime.poll_interval_seconds)
            current = self._wait_for_page(
                PageType.MANOR_HOME,
                f"reward_feed_{rewarded}_after",
                required_elements=("family",),
            )
        result.tasks.append(
            TaskResult(
                "feed_rewards",
                TaskStatus.SUCCESS if rewarded else TaskStatus.SKIPPED,
                f"rewarded {rewarded} feed helper(s)",
            )
        )
        return current

    def _handle_family_feeding(self, result: RunResult, page: DetectedPage) -> DetectedPage:
        current = page
        fed = 0
        while fed < 2:
            key = next((key for key in current.elements if key.startswith("feed_family_")), None)
            if key is None:
                break
            action = self.actions.tap(current, key, f"family_feed_{fed + 1}")
            self._record_action(result, action)
            if action.status.value != "executed":
                raise AutomationError(action.error or "Unable to start family feeding")
            confirm_page = self._wait_for_page(
                PageType.MANOR_HOME, f"family_feed_confirm_{fed + 1}",
                required_elements=("confirm_feed",),
            )
            confirm = self.actions.tap(confirm_page, "confirm_feed", f"confirm_family_feed_{fed + 1}")
            self._record_action(result, confirm)
            if confirm.status.value != "executed":
                raise AutomationError(confirm.error or "Unable to confirm family feeding")
            current = self._wait_for_page(PageType.MANOR_HOME, f"family_feed_after_{fed + 1}")
            fed += 1
        result.tasks.append(TaskResult(
            "family_feeding", TaskStatus.SUCCESS if fed else TaskStatus.SKIPPED,
            f"fed {fed} family chicken(s)",
        ))
        return current

    def _handle_feed_tasks(self, result: RunResult, manor: DetectedPage) -> None:
        if "feed_tasks" not in manor.elements:
            result.tasks.append(TaskResult("feed_tasks", TaskStatus.SKIPPED, "entry not visible"))
            return
        page = self._tap_and_wait(
            result, manor, "feed_tasks", "open_feed_tasks", PageType.MANOR_FEED_TASKS,
            "feed_tasks", required_any_elements=("claim_daily", "daily_claim_done", "quiz", "video"),
        )
        if "claim_daily" in page.elements:
            page = self._claim_feed(result, page, "claim_daily", "daily_feed")
        else:
            result.tasks.append(TaskResult("daily_feed", TaskStatus.ALREADY_DONE, "already claimed"))

        if "quiz" in page.elements:
            quiz = self._tap_and_wait(
                result, page, "quiz", "open_quiz", PageType.MANOR_QUIZ, "quiz",
                required_elements=("answer_a", "answer_b"),
            )
            options = (quiz.elements["answer_a"].text or "", quiz.elements["answer_b"].text or "")
            ignored = {*options, "我们和地球", "题目来源 - 答答星球", "返回"}
            candidates = [label for label in quiz.observation.visible_labels if label not in ignored and "题目来源" not in label]
            if not candidates:
                raise AutomationError("Quiz question text is missing")
            question = max(candidates, key=len)
            answer_index = WebQuizSolver(self.config.quiz).solve(question, options)
            self._log("quiz.answer_selected", question=question, option=options[answer_index])
            answer = self.actions.tap(quiz, f"answer_{'ab'[answer_index]}", "answer_quiz")
            self._record_action(result, answer)
            quiz_result = self._wait_for_page(
                PageType.MANOR_QUIZ_RESULT, "quiz_result", required_elements=("claim_quiz_feed",)
            )
            page = self._tap_and_wait(
                result, quiz_result, "claim_quiz_feed", "leave_quiz", PageType.MANOR_FEED_TASKS,
                "feed_tasks_after_quiz",
            )
            page = self._claim_feed(result, page, "claim_quiz_reward", "quiz_feed")
        else:
            result.tasks.append(TaskResult("quiz", TaskStatus.ALREADY_DONE, "quiz action not present"))

        if "video" in page.elements:
            action = self.actions.tap(page, "video", "open_feed_video")
            self._record_action(result, action)
            complete = self._wait_for_page(
                PageType.MANOR_FEED_VIDEO_COMPLETE,
                "feed_video_complete",
                timeout_seconds=self.config.runtime.external_task_timeout_seconds,
            )
            back = self.actions.back(complete, "leave_feed_video")
            self._record_action(result, back)
            page = self._wait_for_page(PageType.MANOR_FEED_TASKS, "feed_tasks_after_video")
            page = self._claim_feed(result, page, "claim_video_reward", "video_feed")
        else:
            result.tasks.append(TaskResult("feed_video", TaskStatus.ALREADY_DONE, "video action not present"))

        self._handle_manor_lotteries(result, page)

    def _claim_feed(self, result: RunResult, page: DetectedPage, key: str, name: str) -> DetectedPage:
        if key not in page.elements:
            result.tasks.append(TaskResult(name, TaskStatus.ALREADY_DONE, "claim action not present"))
            return page
        action = self.actions.tap(page, key, name)
        self._record_action(result, action)
        if action.status.value != "executed":
            raise AutomationError(action.error or f"Unable to {name}")
        after = self._capture_page(f"{name}_after")
        if after.type is PageType.MANOR_FEED_FULL:
            decline = self.actions.back(after, f"{name}_decline_overflow")
            self._record_action(result, decline)
            after = self._wait_for_page(PageType.MANOR_FEED_TASKS, f"{name}_overflow_closed")
            result.tasks.append(TaskResult(name, TaskStatus.SKIPPED, "feed bag would overflow"))
            return after
        if after.type is not PageType.MANOR_FEED_TASKS:
            after = self._wait_for_page(PageType.MANOR_FEED_TASKS, f"{name}_settled")
        result.tasks.append(TaskResult(name, TaskStatus.SUCCESS, "claimed"))
        return after

    def _handle_manor_lotteries(self, result: RunResult, page: DetectedPage) -> None:
        processed: set[str] = set()
        current = page
        scans = 0
        runner = LotteryRunner(self)
        while len(processed) < 2 and scans < 12:
            choice = next(
                ((key, item) for key, item in current.elements.items()
                 if key.startswith("lottery_") and (item.text or key) not in processed),
                None,
            )
            if choice is None:
                width, height = self.device.screen_size()
                self.device.swipe((width // 2, int(height * 0.78)), (width // 2, int(height * 0.35)), 500)
                self._log("feed_tasks.scroll_for_lottery", scan=scans + 1)
                current = self._capture_page("feed_tasks_lottery_scan")
                scans += 1
                continue
            key, item = choice
            identity = item.text or key
            lottery = self._tap_and_wait(
                result, current, key, f"open_manor_lottery_{len(processed) + 1}",
                PageType.LOTTERY, f"manor_lottery_{len(processed) + 1}",
            )
            runner.run(result, lottery, "task_store", f"manor_lottery_{len(processed) + 1}", 3)
            processed.add(identity)
            back = self.actions.back(lottery, f"leave_manor_lottery_{len(processed)}")
            self._record_action(result, back)
            current = self._wait_for_page(PageType.MANOR_FEED_TASKS, "feed_tasks_after_lottery")
        if len(processed) < 2:
            result.tasks.append(TaskResult(
                "manor_lotteries", TaskStatus.UNKNOWN,
                f"found {len(processed)} of 2 lottery entries after {scans} scans",
            ))

    def _handle_family_donation(
        self,
        result: RunResult,
        family_tasks: DetectedPage,
    ) -> TaskStatus:
        if "donation_done" in family_tasks.elements:
            result.tasks.append(
                TaskResult("family_egg_donation", TaskStatus.ALREADY_DONE, "already donated today")
            )
            return TaskStatus.ALREADY_DONE
        if "donate" not in family_tasks.elements:
            raise AutomationError("Family task panel has no donation action or completed state")

        page = self._tap_and_wait(
            result,
            family_tasks,
            "donate",
            "open_egg_donation",
            PageType.MANOR_DONATION,
            "donation_projects",
            required_elements=("select_project",),
        )
        page = self._tap_and_wait(
            result,
            page,
            "select_project",
            "select_first_donation_project",
            PageType.MANOR_DONATION_PROJECT,
            "donation_project",
            required_elements=("donate_now",),
        )
        page = self._tap_and_wait(
            result,
            page,
            "donate_now",
            "open_donation_confirmation",
            PageType.MANOR_DONATION_CONFIRM,
            "donation_confirmation",
            required_elements=("confirm_donation",),
        )
        reward = self._tap_and_wait(
            result,
            page,
            "confirm_donation",
            "confirm_default_egg_donation",
            PageType.MANOR_DONATION_REWARD,
            "donation_reward",
        )
        result.tasks.append(
            TaskResult("family_egg_donation", TaskStatus.SUCCESS, "donated default quantity: 1 egg")
        )

        project = self._back_and_wait(
            result,
            reward,
            "leave_donation_reward",
            PageType.MANOR_DONATION_PROJECT,
            "donation_project_after_reward",
            required_elements=("donate_now",),
        )
        projects = self._back_and_wait(
            result,
            project,
            "leave_donation_project",
            PageType.MANOR_DONATION,
            "donation_projects_after_reward",
            required_elements=("select_project",),
        )
        self._back_and_wait(
            result,
            projects,
            "leave_donation_projects",
            PageType.MANOR_HOME,
            "manor_after_donation",
            required_elements=("family",),
        )
        return TaskStatus.SUCCESS

    def _tap_and_wait(
        self,
        result: RunResult,
        page: DetectedPage,
        element_key: str,
        action_name: str,
        expected: PageType,
        observation_name: str,
        required_elements: tuple[str, ...] = (),
    ) -> DetectedPage:
        action = self.actions.tap(page, element_key, action_name)
        self._record_action(result, action)
        if action.status.value != "executed":
            raise AutomationError(action.error or f"Action failed: {action_name}")
        return self._wait_for_page(
            expected,
            observation_name,
            required_elements=required_elements,
        )

    def _back_and_wait(
        self,
        result: RunResult,
        page: DetectedPage,
        action_name: str,
        expected: PageType,
        observation_name: str,
        required_elements: tuple[str, ...] = (),
    ) -> DetectedPage:
        action = self.actions.back(page, action_name)
        self._record_action(result, action)
        if action.status.value != "executed":
            raise AutomationError(action.error or f"Action failed: {action_name}")
        return self._wait_for_page(
            expected,
            observation_name,
            required_elements=required_elements,
        )

    def _wait_for_family_tasks(self, name: str) -> DetectedPage:
        return self._wait_for_page(
            PageType.MANOR_FAMILY,
            name,
            required_elements=("close",),
            required_any_elements=("donate", "donation_done"),
        )

    def _wait_for_optional_element(
        self,
        expected: PageType,
        element_key: str,
        name: str,
        timeout_seconds: float,
        required_elements: tuple[str, ...] = (),
    ) -> DetectedPage | None:
        latest: DetectedPage | None = None

        def observe():
            nonlocal latest
            latest = self._capture_page(name)
            return latest.observation

        def matches(_observation) -> bool:
            return (
                latest is not None
                and latest.type is expected
                and element_key in latest.elements
                and all(key in latest.elements for key in required_elements)
            )

        try:
            wait_until(
                observe,
                matches,
                timeout_seconds,
                self.config.runtime.poll_interval_seconds,
            )
        except TimeoutError:
            return None
        return latest

    def _capture_page(self, name: str) -> DetectedPage:
        if self.run_directory is None:
            raise RuntimeError("workflow has not started")
        self._capture_index += 1
        observation = self.observations.observe(
            self.run_directory,
            f"{self._capture_index:03d}-{name}",
        )
        self.recorder.write_observation_metadata(
            self.run_directory, observation, f"{self._capture_index:03d}-{name}"
        )
        page = self.detector.detect(observation)
        self._log(
            "observation.captured",
            name=name,
            page=page.type.value,
            activity=observation.activity,
            elements=sorted(page.elements),
            evidence=list(page.evidence),
            errors=list(observation.errors),
        )
        return page

    def _wait_for_page(
        self,
        expected: PageType,
        name: str,
        required_elements: tuple[str, ...] = (),
        required_any_elements: tuple[str, ...] = (),
        timeout_seconds: float | None = None,
    ) -> DetectedPage:
        latest: DetectedPage | None = None

        def observe():
            nonlocal latest
            latest = self._capture_page(name)
            return latest.observation

        def matches(_observation) -> bool:
            return (
                latest is not None
                and latest.type is expected
                and all(key in latest.elements for key in required_elements)
                and (
                    not required_any_elements
                    or any(key in latest.elements for key in required_any_elements)
                )
            )

        observation = wait_until(
            observe,
            matches,
            timeout_seconds or self.config.runtime.page_timeout_seconds,
            self.config.runtime.poll_interval_seconds,
        )
        assert latest is not None
        return latest

    def _finish(self, result: RunResult, status: TaskStatus, detail: str | None) -> RunResult:
        result.status = status
        result.finished_at = datetime.now(timezone.utc)
        if detail and status in {TaskStatus.UNKNOWN, TaskStatus.FAILED}:
            result.error = {"type": status.value, "message": detail}
        result.tasks.append(TaskResult("manor_daily", status, detail))
        result.actions.extend(item for item in self.actions.results if item not in result.actions)
        self._log(
            "workflow.finish",
            status=status.value,
            detail=detail,
            tasks=[f"{item.name}:{item.status.value}" for item in result.tasks],
            actions=[f"{item.name}:{item.status.value}" for item in result.actions],
        )
        if self.run_directory is not None:
            self.recorder.write_result(self.run_directory, result)
        return result

    def _record_action(self, result: RunResult, action: ActionResult) -> None:
        result.actions.append(action)
        self._log(
            "action.completed",
            action=action.name,
            status=action.status.value,
            point=action.point,
            error=action.error,
        )

    def _log(self, event: str, **fields) -> None:
        if self.log is not None:
            self.log.info(event, **fields)
