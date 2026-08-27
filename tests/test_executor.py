from __future__ import annotations

from conftest import make_observation

from action_executor import ActionExecutor
from device_bridge.common import Size
from domain_data import (
    Action,
    ActionKind,
    ActionStatus,
    Bounds,
    DetectedScreen,
    Element,
    Overlay,
    OverlayType,
    Page,
)


class _Device:
    def __init__(self):
        self.taps: list[tuple[int, int]] = []

    def size(self):
        return Size(1440, 3200)

    def tap(self, point):
        self.taps.append(point)

    def back(self):
        self.backs = getattr(self, "backs", []) + [True]

    def current_package_activity(self):
        return "com.eg.android.AlipayGphone", "Activity"


class _Collector:
    def __init__(self, screen: DetectedScreen):
        self.screen = screen

    def capture(self, *_args, **_kwargs):
        return self.screen.observation


class _Detector:
    def __init__(self, screen: DetectedScreen):
        self.screen = screen

    def detect(self, _observation):
        return self.screen


class _Logger:
    def emit(self, *_args, **_kwargs):
        pass


def _element(key: str) -> Element:
    return Element(key, Bounds(600, 2500, 840, 2700), "obs-1")


def _observation():
    return make_observation("<?xml version='1.0'?><hierarchy rotation='0' />")


def _screen(overlays: tuple[Overlay, ...]) -> tuple[DetectedScreen, DetectedScreen]:
    after = DetectedScreen(
        Page.FOREST_HOME,
        _observation(),
        {"love_plant": _element("love_plant")},
        (),
        ("ui:蚂蚁森林",),
        0.9,
    )
    return DetectedScreen(
        Page.FOREST_HOME,
        _observation(),
        {"love_plant": _element("love_plant")},
        overlays,
        ("ui:蚂蚁森林",),
        0.9,
    ), after


def _executor(screen: DetectedScreen, after: DetectedScreen) -> ActionExecutor:
    return ActionExecutor(
        _Device(),
        _Collector(after),
        _Detector(after),
        _Logger(),
        None,
        "com.eg.android.AlipayGphone",
        settle_seconds=0.0,
    )


def _promo_overlay() -> Overlay:
    close = Element("close", Bounds(652, 2664, 792, 2804), "obs-1", "关闭")
    return Overlay(OverlayType.PROMO, {"close": close}, ("cv:modal_scrim",), 0.9)


def test_tap_on_page_element_under_promo_is_refused_before_any_touch():
    screen, after = _screen((_promo_overlay(),))
    executor = _executor(screen, after)

    result, cancelled = executor.execute(
        screen, Action("forest-love-plant-open", ActionKind.TAP, "love_plant")
    )

    assert result.status is ActionStatus.REJECTED
    assert result.point is None
    assert "overlay" in (result.error or "")
    assert cancelled is None
    assert executor.device.taps == []


def test_tap_on_promo_close_control_is_allowed():
    screen, after = _screen((_promo_overlay(),))
    executor = _executor(screen, after)

    result, observed = executor.execute(
        screen, Action("recovery-dismiss-promo", ActionKind.TAP, "close")
    )

    assert result.status is ActionStatus.EXECUTED
    assert result.point == (722, 2734)
    assert observed is after
    assert executor.device.taps == [(722, 2734)]


def test_tap_without_overlay_is_unaffected():
    screen, after = _screen(())
    executor = _executor(screen, after)

    result, observed = executor.execute(
        screen, Action("forest-love-plant-open", ActionKind.TAP, "love_plant")
    )

    assert result.status is ActionStatus.EXECUTED
    assert observed is after
    assert executor.device.taps == [(720, 2600)]


def test_back_is_allowed_on_unknown_pages():
    observation = make_observation("<?xml version='1.0'?><hierarchy rotation='0' />")
    unknown = DetectedScreen(Page.UNKNOWN, observation, evidence=("no_page_rule_matched",))
    after = DetectedScreen(
        Page.FOREST_HOME,
        make_observation("<?xml version='1.0'?><hierarchy rotation='0' />"),
        evidence=("ui:蚂蚁森林",),
    )
    executor = _executor(unknown, after)

    result, observed = executor.execute(unknown, Action("recovery-back", ActionKind.BACK))

    assert result.status is ActionStatus.EXECUTED
    assert observed is after
