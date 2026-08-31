from __future__ import annotations

import time
from collections.abc import Callable

from device_bridge.adb import AndroidDevice
from domain_data import (
    Action,
    ActionKind,
    ActionResult,
    ActionStatus,
    DetectedScreen,
    OverlayType,
    Page,
)
from logger import RunLogger
from runtime.errors import SafetyStop
from screen_perception import ObservationCollector, ObservationMode, ScreenDetector

Postcondition = Callable[[DetectedScreen], bool]


class ActionExecutor:
    def __init__(
        self,
        device: AndroidDevice,
        collector: ObservationCollector,
        detector: ScreenDetector,
        logger: RunLogger,
        artifacts_directory,
        package: str,
        settle_seconds: float = 1.0,
    ):
        self.device = device
        self.collector = collector
        self.detector = detector
        self.logger = logger
        self.artifacts_directory = artifacts_directory
        self.package = package
        self.settle_seconds = settle_seconds

    def execute(
        self,
        screen: DetectedScreen,
        action: Action,
        expected_pages: tuple[Page, ...] = (),
        postcondition: Postcondition | None = None,
        observe_after: bool = True,
    ) -> tuple[ActionResult, DetectedScreen | None]:
        started = time.perf_counter()
        point: tuple[int, int] | None = None
        try:
            self._validate_screen(screen, action)
            if action.kind is ActionKind.TAP:
                if not action.element_key:
                    raise SafetyStop("Tap action has no element key")
                element = screen.element(action.element_key)
                if element is None:
                    raise SafetyStop(f"Element not found: {action.element_key}")
                if element.observation_id != screen.observation.id:
                    raise SafetyStop(f"Element is stale: {action.element_key}")
                if not element.enabled or not element.clickable or not element.bounds.valid:
                    raise SafetyStop(f"Element is not executable: {action.element_key}")
                blocking = [
                    overlay.type.value
                    for overlay in screen.overlays
                    if overlay.type is OverlayType.PROMO
                    and action.element_key not in overlay.elements
                ]
                if blocking:
                    # The promo scrim swallows every touch, so the page element
                    # underneath cannot receive this tap. Refuse before anything
                    # is sent so recovery can dismiss the promo and retry.
                    raise SafetyStop(f"Refusing tap under overlay: {', '.join(blocking)}")
                point = element.center
                if not self.device.size().contains(point):
                    raise SafetyStop(f"Element lies outside the current screen: {point}")
                self.device.tap(point)
            elif action.kind is ActionKind.SWIPE:
                if action.start is None or action.end is None:
                    raise SafetyStop("Swipe action is missing coordinates")
                self.device.swipe(action.start, action.end, action.duration_ms)
            elif action.kind is ActionKind.BACK:
                self.device.back()
            elif action.kind is ActionKind.WAIT:
                pass
            else:
                raise SafetyStop(f"Unsupported action: {action.kind}")
            after = None
            if observe_after:
                time.sleep(self.settle_seconds)
                observation = self.collector.capture(
                    self.artifacts_directory,
                    f"after-{action.name}",
                    self._after_observation_mode(),
                )
                after = self.detector.detect(observation)
                unstable_after = _unstable(after) and not _allows_dynamic_friend_transition(
                    screen, action, after, expected_pages
                )
                page_mismatch = bool(expected_pages and after.page not in expected_pages)
                postcondition_failed = bool(
                    postcondition is not None and not postcondition(after)
                )
                if unstable_after or page_mismatch or postcondition_failed:
                    # WebView transitions can leave the old page rendered for
                    # one or two frames after a tap (notably the forest sign
                    # reward and Canvas modals).  Give the expected page a
                    # short, bounded confirmation window before treating the
                    # action as rejected; this avoids unnecessary retries
                    # while keeping the action atomic.
                    for confirmation in range(2):
                        time.sleep(self.settle_seconds)
                        observation = self.collector.capture(
                            self.artifacts_directory,
                            f"after-{action.name}-confirm-{confirmation + 1}",
                            self._after_observation_mode(),
                        )
                        after = self.detector.detect(observation)
                        if (
                            (
                                not _unstable(after)
                                or _allows_dynamic_friend_transition(
                                    screen, action, after, expected_pages
                                )
                            )
                            and (not expected_pages or after.page in expected_pages)
                            and (postcondition is None or postcondition(after))
                        ):
                            break
                    if _unstable(after) and not _allows_dynamic_friend_transition(
                        screen, action, after, expected_pages
                    ):
                        raise SafetyStop(
                            f"Unstable postcondition observation after {action.name}"
                        )
                    if expected_pages and after.page not in expected_pages:
                        raise SafetyStop(
                            f"Postcondition page mismatch after {action.name}: "
                            f"expected {[item.value for item in expected_pages]}, got {after.page.value}"
                        )
                    if postcondition is not None and not postcondition(after):
                        raise SafetyStop(f"Postcondition failed after {action.name}")
            result = ActionResult(
                action.name,
                ActionStatus.EXECUTED,
                screen.observation.id,
                after.observation.id if after else None,
                point,
                elapsed_ms=(time.perf_counter() - started) * 1000,
            )
        except SafetyStop as exc:
            after = None
            result = ActionResult(
                action.name,
                ActionStatus.REJECTED,
                screen.observation.id,
                point=point,
                error=str(exc),
                elapsed_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception as exc:
            after = None
            result = ActionResult(
                action.name,
                ActionStatus.FAILED,
                screen.observation.id,
                point=point,
                error=str(exc),
                elapsed_ms=(time.perf_counter() - started) * 1000,
            )
        self.logger.emit(
            "action.completed",
            name=result.name,
            status=result.status.value,
            before=result.before_observation_id,
            after=result.after_observation_id,
            point=result.point,
            error=result.error,
            elapsed_ms=round(result.elapsed_ms, 2),
        )
        return result, after

    def _validate_screen(self, screen: DetectedScreen, action: Action) -> None:
        if screen.page is Page.UNKNOWN and action.kind is not ActionKind.BACK:
            # Unknown pages refuse coordinate actions; Back is the one safe
            # universal exit and stays allowed so recovery can leave ads.
            raise SafetyStop("Refusing action on unknown page")
        if screen.observation.package != self.package:
            raise SafetyStop(f"Foreground package is not Alipay: {screen.observation.package}")
        unstable = _unstable(screen)
        safe_friend_advance = (
            screen.page is Page.FOREST_FRIEND and action.kind is ActionKind.SWIPE
        )
        if unstable and not safe_friend_advance:
            raise SafetyStop("Observation changed while it was captured")
        package, activity = self.device.current_package_activity()
        if package != self.package:
            raise SafetyStop(f"Alipay is no longer foreground: {package}")
        if (
            screen.observation.activity is not None
            and activity != screen.observation.activity
        ):
            raise SafetyStop(
                "Foreground Activity changed since observation: "
                f"expected {screen.observation.activity}, got {activity}"
            )

    def _after_observation_mode(self) -> ObservationMode:
        """Avoid stability retries on an intentionally moving live-video page."""
        try:
            package, activity = self.device.current_package_activity()
        except Exception:
            return ObservationMode.FULL
        if package == self.package and (activity or "").endswith(
            "LivingDetailActivity"
        ):
            return ObservationMode.FAST
        return ObservationMode.FULL


def _unstable(screen: DetectedScreen) -> bool:
    return any(
        error.startswith("unstable_observation")
        for error in screen.observation.errors
    )


def _allows_dynamic_friend_transition(
    before: DetectedScreen,
    action: Action,
    after: DetectedScreen,
    expected_pages: tuple[Page, ...],
) -> bool:
    """Friend-to-friend swipe animation is coherent without a static frame."""
    if not expected_pages or after.page not in expected_pages:
        return False
    return (
        before.page is Page.FOREST_FRIEND
        and action.kind is ActionKind.SWIPE
    ) or (
        before.page is Page.FOREST_HOME
        and action.kind is ActionKind.TAP
        and action.element_key == "find_energy"
        and after.page is Page.FOREST_FRIEND
    )
