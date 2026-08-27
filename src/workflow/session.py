from __future__ import annotations

import json
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timezone

from action_executor import ActionExecutor
from device_bridge.adb import AndroidDevice
from domain_data import (
    Action,
    ActionKind,
    ActionResult,
    ActionStatus,
    DetectedScreen,
    Page,
    RunResult,
    StepResult,
    StepStatus,
)
from logger import RunLogger
from runtime.config import Config
from runtime.errors import AutomationError, StepTimeout
from runtime.state_store import StateStore
from screen_perception import ObservationCollector, ObservationMode, ScreenDetector
from workflow.recovery import RecoveryPolicy


class WorkflowSession:
    def __init__(self, name: str, device: AndroidDevice, config: Config):
        self.name = name
        self.device = device
        self.config = config
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        self.run_directory = config.runtime.screenshots_directory / self.run_id
        self.logger = RunLogger(config.runtime.logs_directory, self.run_id)
        self.collector = ObservationCollector(device, self.logger)
        self.detector = ScreenDetector(config.package, config.perception.template_directory)
        self.actions = ActionExecutor(
            device,
            self.collector,
            self.detector,
            self.logger,
            self.run_directory,
            config.package,
            config.runtime.settle_seconds,
        )
        self.store = StateStore(config.runtime.state_database)
        self.result = RunResult(
            self.run_id,
            name,
            StepStatus.IN_PROGRESS,
            datetime.now(timezone.utc),
        )
        self.current: DetectedScreen | None = None
        self.recovery = RecoveryPolicy(self)
        self._recovering = False

    def start(self) -> None:
        if not self.store.acquire_lock("daily", self.run_id):
            raise AutomationError("Another daily workflow holds the process lock")
        self.logger.emit("workflow.started", workflow=self.name, run_id=self.run_id, device=self.device.serial)

    def finish(self, status: StepStatus, error: str | None = None) -> RunResult:
        self.result.status = status
        self.result.error = error
        self.result.finished_at = datetime.now(timezone.utc)
        self.store.release_lock("daily", self.run_id)
        self.logger.emit("workflow.finished", status=status.value, error=error)
        self.run_directory.mkdir(parents=True, exist_ok=True)
        (self.run_directory / "result.json").write_text(
            json.dumps(self.result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return self.result

    def observe(self, reason: str, fast: bool = False) -> DetectedScreen:
        observation = self.collector.capture(
            self.run_directory,
            reason,
            ObservationMode.FAST if fast else ObservationMode.FULL,
        )
        self.current = self.detector.detect(observation)
        self.logger.emit(
            "screen.detected",
            page=self.current.page.value,
            overlays=[overlay.type.value for overlay in self.current.overlays],
            elements=sorted(self.current.elements),
            evidence=list(self.current.evidence),
        )
        return self.current

    def wait_for(
        self,
        pages: Page | tuple[Page, ...],
        reason: str,
        required: tuple[str, ...] = (),
        timeout: float | None = None,
    ) -> DetectedScreen:
        expected = (pages,) if isinstance(pages, Page) else pages
        deadline = time.monotonic() + (timeout or self.config.runtime.page_timeout_seconds)
        latest = None
        while time.monotonic() < deadline:
            latest = self.observe(reason)
            if latest.page in expected and all(latest.element(key) is not None for key in required):
                return latest
            time.sleep(self.config.runtime.poll_interval_seconds)
        # Nothing was sent to the device while waiting, so a transient overlay
        # or slow page load may simply have masked the target. Try one recovery
        # pass before declaring the wait failed.
        if expected and latest is not None:
            recovered = self.recover(expected)
            if all(recovered.element(key) is not None for key in required):
                return recovered
            detail = recovered.page.value
        else:
            detail = latest.page.value if latest else "none"
        raise StepTimeout(f"Timed out waiting for {[page.value for page in expected]}; latest={detail}")

    def _tap_raw(
        self,
        screen: DetectedScreen,
        key: str,
        name: str,
        expected: tuple[Page, ...] = (),
        required_after: tuple[str, ...] = (),
    ) -> tuple[ActionResult, DetectedScreen | None]:
        """Execute a tap with no recovery; return the result and next screen.

        ``tap`` wraps this with one recovery-and-retry pass. Recovery and
        overlay dismissal call this directly so a failed dismiss can never
        recurse into another recovery attempt.
        """
        result, after = self.actions.execute(
            screen,
            Action(name, ActionKind.TAP, key),
            expected,
            (lambda page: all(page.element(item) is not None for item in required_after)) if required_after else None,
        )
        self.result.actions.append(result)
        if result.status is ActionStatus.EXECUTED and after is not None:
            self.current = after
        return result, after

    def tap(
        self,
        screen: DetectedScreen,
        key: str,
        name: str,
        expected: tuple[Page, ...] = (),
        required_after: tuple[str, ...] = (),
    ) -> DetectedScreen:
        result, after = self._tap_raw(screen, key, name, expected, required_after)
        if result.status is ActionStatus.EXECUTED and after is not None:
            return after
        # Retry only when nothing was sent to the device (point is None) and we
        # know the target page. Recover the source page before looking up and
        # tapping the source element again; ``expected`` describes the page
        # after the tap and is therefore not a valid recovery target here.
        # A point that is already set means the tap fired,
        # so retrying could repeat an irreversible action such as donating an
        # egg — that is never allowed (design §6).
        if (
            not self._recovering
            and expected
            and result.status is ActionStatus.REJECTED
            and result.point is None
        ):
            self._recovering = True
            try:
                recovered = self.recover((screen.page,))
                result, after = self._tap_raw(recovered, key, name, expected, required_after)
            finally:
                self._recovering = False
            if result.status is ActionStatus.EXECUTED and after is not None:
                return after
        raise AutomationError(result.error or f"Action failed: {name}")

    def recover(
        self,
        allowed_pages: tuple[Page, ...],
        reenter: Callable[[], DetectedScreen] | None = None,
    ) -> DetectedScreen:
        """Re-observe, dismiss known overlays and back out to an allowed page.

        ``reenter`` lets a task re-open its entry point (design §7 step 5);
        leaving it ``None`` covers the common case of a transient overlay or
        slow load sitting on top of the expected page.
        """
        if self.current is None:
            raise AutomationError("Cannot recover without a prior observation")
        return self.recovery.recover(self.current, allowed_pages, reenter)

    def back(self, screen: DetectedScreen, name: str, expected: tuple[Page, ...] = ()) -> DetectedScreen:
        result, after = self.actions.execute(screen, Action(name, ActionKind.BACK), expected)
        self.result.actions.append(result)
        if result.status is not ActionStatus.EXECUTED or after is None:
            raise AutomationError(result.error or f"Action failed: {name}")
        self.current = after
        return after

    def swipe(
        self,
        screen: DetectedScreen,
        name: str,
        start: tuple[int, int],
        end: tuple[int, int],
        duration_ms: int = 400,
    ) -> DetectedScreen:
        result, after = self.actions.execute(
            screen,
            Action(name, ActionKind.SWIPE, start=start, end=end, duration_ms=duration_ms),
        )
        self.result.actions.append(result)
        if result.status is not ActionStatus.EXECUTED or after is None:
            raise AutomationError(result.error or f"Action failed: {name}")
        self.current = after
        return after

    def swipe_without_observation(
        self,
        screen: DetectedScreen,
        name: str,
        start: tuple[int, int],
        end: tuple[int, int],
        duration_ms: int = 400,
    ) -> None:
        """Issue a validated swipe while retaining the last known page.

        This is reserved for short bursts on an already classified timed-ad
        page; the caller must take a fresh observation immediately afterwards.
        """
        result, _ = self.actions.execute(
            screen,
            Action(name, ActionKind.SWIPE, start=start, end=end, duration_ms=duration_ms),
            observe_after=False,
        )
        self.result.actions.append(result)
        if result.status is not ActionStatus.EXECUTED:
            raise AutomationError(result.error or f"Action failed: {name}")

    def return_from_unclassified(self, source_page: Page, reason: str) -> DetectedScreen:
        """Use one context-bound Back after a known navigation."""
        package, _ = self.device.current_package_activity()
        if package != self.config.package:
            raise AutomationError(f"Cannot safely return from foreground package: {package}")
        self.device.back()
        return self.wait_for(source_page, reason)

    def add_step(self, name: str, status: StepStatus, detail: str | None = None, attempts: int = 1) -> None:
        result = StepResult(name, status, detail, attempts)
        self.result.steps.append(result)
        observation_id = self.current.observation.id if self.current else None
        self.store.save_step(self.run_id, self.name, name, status, observation_id, detail)
        self.logger.emit("step.finished", step=name, status=status.value, detail=detail, attempts=attempts)
