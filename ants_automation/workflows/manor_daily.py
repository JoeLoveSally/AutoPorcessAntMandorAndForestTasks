from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import time

from ..actions.executor import ActionExecutor
from ..device.adb import AndroidDevice
from ..domain.models import DetectedPage, PageType, RunResult, TaskResult, TaskStatus
from ..evidence.recorder import EvidenceRecorder
from ..perception.detector import PageDetector
from ..perception.observation import ObservationCollector
from ..runtime.config import Config
from ..runtime.errors import AutomationError, TimeoutError
from ..runtime.wait import wait_until


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
        self._capture_index = 0

    @classmethod
    def create(cls, device: AndroidDevice, config: Config) -> "ManorDailyWorkflow":
        return cls(device, config, PageDetector(), EvidenceRecorder(config.runtime.artifacts_directory))

    def run(self) -> RunResult:
        started = datetime.now(timezone.utc)
        result = RunResult("manor_daily", TaskStatus.UNKNOWN, started)
        self.run_directory = self.recorder.new_run()
        result.evidence_directory = self.run_directory
        try:
            self.device.launch_package(self.config.package)
            time.sleep(self.config.runtime.launch_wait_seconds)
            home = self._capture_page("alipay_home")
            if home.type is not PageType.ALIPAY_HOME:
                return self._finish(result, TaskStatus.UNKNOWN, "Alipay home not recognized")

            manor_action = self.actions.tap(home, "manor", "open_manor")
            result.actions.append(manor_action)
            if manor_action.status.value != "executed":
                return self._finish(result, TaskStatus.FAILED, manor_action.error)
            manor = self._wait_for_page(PageType.MANOR_HOME, "manor_home")

            family = manor.elements.get("family")
            if family is None:
                return self._finish(
                    result,
                    TaskStatus.UNKNOWN,
                    "MANOR_HOME has no registered Family element; collect visual evidence before adding a locator",
                )
            family_action = self.actions.tap(manor, "family", "open_family")
            result.actions.append(family_action)
            if family_action.status.value != "executed":
                return self._finish(result, TaskStatus.FAILED, family_action.error)
            family_page = self._wait_for_page(PageType.MANOR_FAMILY, "family")

            sign_in = family_page.elements.get("sign_in")
            if sign_in is None:
                return self._finish(result, TaskStatus.UNKNOWN, "Family page has no registered sign-in state")
            sign_action = self.actions.tap(family_page, "sign_in", "sign_in")
            result.actions.append(sign_action)
            if sign_action.status.value != "executed":
                return self._finish(result, TaskStatus.FAILED, sign_action.error)
            return self._finish(
                result,
                TaskStatus.UNKNOWN,
                "Sign-in action executed; success state needs real-page evidence",
            )
        except AutomationError as exc:
            return self._finish(result, TaskStatus.FAILED, str(exc))
        except Exception as exc:
            return self._finish(result, TaskStatus.FAILED, str(exc))

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
        return self.detector.detect(observation)

    def _wait_for_page(self, expected: PageType, name: str) -> DetectedPage:
        latest: DetectedPage | None = None

        def observe():
            nonlocal latest
            latest = self._capture_page(name)
            return latest.observation

        def matches(_observation) -> bool:
            return latest is not None and latest.type is expected

        observation = wait_until(
            observe,
            matches,
            self.config.runtime.page_timeout_seconds,
            self.config.runtime.poll_interval_seconds,
        )
        assert latest is not None
        return latest

    def _finish(self, result: RunResult, status: TaskStatus, detail: str | None) -> RunResult:
        result.status = status
        result.finished_at = datetime.now(timezone.utc)
        if detail:
            result.error = {"type": status.value, "message": detail}
        result.tasks.append(TaskResult("manor_daily", status, detail))
        result.actions.extend(item for item in self.actions.results if item not in result.actions)
        if self.run_directory is not None:
            self.recorder.write_result(self.run_directory, result)
        return result
