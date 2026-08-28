from __future__ import annotations

import time
from typing import TYPE_CHECKING

from domain_data import DetectedScreen, OverlayType, Page
from runtime.errors import AutomationError

if TYPE_CHECKING:
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
            # Activity-level advertisements and promotional pages commonly do
            # not expose a reliable close control.  Back is the safest and
            # most portable dismissal because Alipay normally restores the
            # page that launched the ad.  If Back is unavailable or does not
            # clear the overlay, the normal close-button handling below (or a
            # later recovery attempt) remains as a fallback.
            promo = next(
                (overlay for overlay in reversed(current.overlays)
                 if overlay.type in (OverlayType.PROMO, OverlayType.UNKNOWN)),
                None,
            )
            if promo is not None:
                try:
                    backed = self.session.back(current, f"recovery-back-{attempt}")
                    current = backed
                    if current.page in allowed_pages and not current.overlays:
                        return current
                    # Re-observe on the next attempt so a transient ad/page
                    # transition is not mistaken for a failed source page.
                    continue
                except AutomationError:
                    # Some test doubles/device states cannot issue Back; fall
                    # through to a semantic close control when one exists.
                    pass
            for overlay in reversed(current.overlays):
                key = next(
                    (
                        candidate
                        for candidate in (
                            "abandon_reward",
                            "close_reward",
                            "confirm_overflow",
                            "close",
                        )
                        if candidate in overlay.elements
                    ),
                    None,
                )
                if key and overlay.type is not OverlayType.UNKNOWN:
                    # Dismiss via the non-recovering primitive so a failed
                    # dismissal cannot recurse into another recovery attempt.
                    try:
                        _, after = self.session._tap_raw(
                            current, key, f"recovery-dismiss-{overlay.type.value}"
                        )
                        if after is not None:
                            current = after
                    except AutomationError:
                        pass
                    break
            else:
                # Unknown pages are activity ads in practice, and one Back is
                # the safe universal exit; the next attempt re-observes and the
                # budget still bounds the whole ladder.
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
