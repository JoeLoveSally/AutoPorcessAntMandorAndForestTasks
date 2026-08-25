from __future__ import annotations

import time

from domain_data import DetectedScreen, OverlayType, Page
from runtime.errors import AutomationError
from workflow.session import WorkflowSession


class RecoveryPolicy:
    def __init__(self, session: WorkflowSession):
        self.session = session

    def recover(
        self,
        screen: DetectedScreen,
        allowed_pages: tuple[Page, ...],
        reenter=None,
    ) -> DetectedScreen:
        current = screen
        for attempt in range(1, self.session.config.runtime.max_recovery_attempts + 1):
            self.session.logger.emit("recovery.attempt", attempt=attempt, page=current.page.value)
            time.sleep(self.session.config.runtime.settle_seconds)
            current = self.session.observe(f"recovery-{attempt}")
            if current.page in allowed_pages and not current.overlays:
                return current
            for overlay in reversed(current.overlays):
                key = next(
                    (
                        candidate
                        for candidate in ("abandon_reward", "close_reward", "confirm_overflow")
                        if candidate in overlay.elements
                    ),
                    None,
                )
                if key and overlay.type is not OverlayType.UNKNOWN:
                    current = self.session.tap(current, key, f"recovery-dismiss-{overlay.type.value}")
                    break
            else:
                if current.page is not Page.UNKNOWN:
                    try:
                        current = self.session.back(current, f"recovery-back-{attempt}")
                    except AutomationError:
                        pass
            if current.page in allowed_pages:
                return current
            if reenter is not None:
                current = reenter()
                if current.page in allowed_pages:
                    return current
        raise AutomationError(f"Recovery budget exhausted; latest={current.page.value}")
