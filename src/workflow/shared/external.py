from __future__ import annotations

import time

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
    ) -> DetectedScreen:
        current = self.session.tap(source, key, f"{name}-open")
        deadline = time.monotonic() + timeout_seconds
        width, height = self.session.device.size().width, self.session.device.size().height
        while time.monotonic() < deadline:
            for overlay in reversed(current.overlays):
                if overlay.type is OverlayType.PRODUCT_QUIZ and "abandon_reward" in overlay.elements:
                    current = self.session.tap(current, "abandon_reward", f"{name}-abandon-popup")
                    break
            if current.page is source_page:
                return current
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
