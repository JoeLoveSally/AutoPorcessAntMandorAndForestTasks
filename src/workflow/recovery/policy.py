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
        *,
        required: tuple[str, ...] = (),
        required_any: tuple[str, ...] = (),
        forbidden: tuple[str, ...] = (),
        activity: str | None = None,
    ) -> DetectedScreen:
        current = screen
        for attempt in range(1, self.session.config.runtime.max_recovery_attempts + 1):
            self.session.logger.emit("recovery.attempt", attempt=attempt, page=current.page.value)
            time.sleep(self.session.config.runtime.settle_seconds)
            current = self.session.observe(f"recovery-{attempt}")
            if _matches_context(
                current,
                allowed_pages,
                required,
                required_any,
                forbidden,
                activity,
            ):
                return current
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
            if _matches_context(
                current,
                allowed_pages,
                required,
                required_any,
                forbidden,
                activity,
            ):
                return current
            if reenter is not None:
                current = reenter()
                if _matches_context(
                    current,
                    allowed_pages,
                    required,
                    required_any,
                    forbidden,
                    activity,
                ):
                    return current
        raise AutomationError(f"Recovery budget exhausted; latest={current.page.value}")


def _matches_context(
    screen: DetectedScreen,
    pages: tuple[Page, ...],
    required: tuple[str, ...],
    required_any: tuple[str, ...],
    forbidden: tuple[str, ...],
    activity: str | None,
) -> bool:
    """Require a usable task context, not merely a matching page enum."""
    stable = not any(
        error.startswith("unstable_observation")
        for error in screen.observation.errors
    )
    return (
        screen.page in pages
        and stable
        and not screen.overlays
        and (activity is None or screen.observation.activity == activity)
        and all(screen.element(key) is not None for key in required)
        and (not required_any or any(screen.element(key) is not None for key in required_any))
        and all(screen.element(key) is None for key in forbidden)
    )
