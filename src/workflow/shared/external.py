from __future__ import annotations

import time
from collections.abc import Callable

from domain_data import DetectedScreen, OverlayType, Page
from runtime.errors import AutomationError, StepTimeout
from workflow.session import WorkflowSession


class ExternalTaskRunner:
    def __init__(self, session: WorkflowSession):
        self.session = session

    def run(
        self,
        source: DetectedScreen,
        key: str,
        name: str,
        source_page: Page,
        *,
        swipe_to_progress: bool,
        immediate_return: bool = False,
        timeout_seconds: float = 45.0,
        reenter: Callable[[], DetectedScreen] | None = None,
    ) -> DetectedScreen:
        opened_at = time.monotonic()
        current = self.session.tap(
            source,
            key,
            f"{name}-open",
            (source_page, Page.EXTERNAL_BROWSE, Page.UNKNOWN),
            reenter=reenter,
        )
        deadline = time.monotonic() + timeout_seconds
        width, height = self.session.device.size().width, self.session.device.size().height
        while time.monotonic() < deadline:
            for overlay in reversed(current.overlays):
                if overlay.type is OverlayType.PRODUCT_QUIZ and "abandon_reward" in overlay.elements:
                    current = self.session.tap(
                        current,
                        "abandon_reward",
                        f"{name}-abandon-popup",
                        (current.page,),
                        reenter=reenter,
                    )
                    break
            # WebViews can retain the task-list DOM after launching a sibling
            # Activity.  A matching Page is a real return only when Activity
            # also matches the source context.
            same_activity = (
                source.observation.activity is None
                or current.observation.activity == source.observation.activity
            )
            if current.page is source_page and same_activity:
                return current
            if (
                (current.observation.activity or "").endswith("LivingDetailActivity")
                and time.monotonic() - opened_at >= 18.0
            ):
                # The short-video Activity continuously animates and its UI
                # tree can remain the source feed-list DOM. Completion is the
                # fixed 15-second dwell; allow three extra seconds, then leave.
                # A promotion may be above the video, so one Back can dismiss
                # it and a second Back can return to the task list.
                for attempt in range(1, 3):
                    self.session.device.back()
                    time.sleep(self.session.config.runtime.settle_seconds)
                    package, activity = self.session.device.current_package_activity()
                    current = self.session.observe(
                        f"{name}-timed-return-{attempt}",
                        fast=(
                            package == self.session.config.package
                            and (activity or "").endswith("LivingDetailActivity")
                        ),
                    )
                    same_activity = (
                        source.observation.activity is None
                        or current.observation.activity == source.observation.activity
                    )
                    if current.page is source_page and same_activity:
                        return current
                raise AutomationError(
                    f"{name} did not return from the completed short-video Activity"
                )
            if immediate_return:
                if current.page is Page.UNKNOWN:
                    return self.session.return_from_unclassified(
                        source_page, f"{name}-return-unclassified"
                    )
                self.session.device.back()
                return self.session.wait_for(source_page, f"{name}-return")
            if current.page is Page.EXTERNAL_BROWSE and current.element("back"):
                return self.session.back(current, f"{name}-return", (source_page,))
            if current.page is Page.EXTERNAL_BROWSE and current.element("close"):
                return self.session.tap(current, "close", f"{name}-close", (source_page,))
            if current.page is Page.UNKNOWN:
                raise AutomationError(f"{name} page is unknown; refusing timed swipe")
            if swipe_to_progress:
                for burst in range(3):
                    self.session.swipe_without_observation(
                        current,
                        f"{name}-progress-swipe-{burst + 1}",
                        (width // 2, int(height * 0.68)),
                        (width // 2, int(height * 0.48)),
                        300,
                    )
                    time.sleep(1.0)
                current = self.session.observe(f"{name}-progress-check")
            else:
                time.sleep(self.session.config.runtime.poll_interval_seconds)
                current = self.session.observe(f"{name}-wait")
        raise StepTimeout(f"Timed out waiting for external task: {name}")
