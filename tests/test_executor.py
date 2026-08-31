from __future__ import annotations

from dataclasses import replace

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
    def __init__(self, activity: str = "Activity"):
        self.taps: list[tuple[int, int]] = []
        self.swipes: list[tuple[tuple[int, int], tuple[int, int], int]] = []
        self.activity = activity

    def size(self):
        return Size(1440, 3200)

    def tap(self, point):
        self.taps.append(point)

    def back(self):
        self.backs = getattr(self, "backs", []) + [True]

    def swipe(self, start, end, duration_ms):
        self.swipes.append((start, end, duration_ms))

    def current_package_activity(self):
        return "com.eg.android.AlipayGphone", self.activity


class _Collector:
    def __init__(self, screen: DetectedScreen, sequence=None):
        self.screen = screen
        self.sequence = list(sequence or ())

    def capture(self, *_args, **_kwargs):
        if self.sequence:
            return self.sequence.pop(0).observation
        return self.screen.observation


class _Detector:
    def __init__(self, screen: DetectedScreen, sequence=None):
        self.screen = screen
        self.sequence = list(sequence or ())

    def detect(self, _observation):
        if self.sequence:
            return self.sequence.pop(0)
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


def test_expected_page_gets_short_confirmation_window():
    screen, after = _screen(())
    stale = DetectedScreen(Page.FOREST_HOME, _observation())
    expected = DetectedScreen(Page.FOREST_LOVE_PLANT, _observation())
    executor = ActionExecutor(
        _Device(),
        _Collector(after),
        _Detector(after, [stale, expected]),
        _Logger(),
        None,
        "com.eg.android.AlipayGphone",
        settle_seconds=0.0,
    )

    result, observed = executor.execute(
        screen,
        Action("open-love-plant", ActionKind.TAP, "love_plant"),
        expected_pages=(Page.FOREST_LOVE_PLANT,),
    )

    assert result.status is ActionStatus.EXECUTED
    assert observed is expected


def test_unstable_expected_page_must_be_confirmed_before_it_is_accepted():
    screen, after = _screen(())
    unstable_observation = replace(
        _observation(),
        errors=("unstable_observation:page changed during capture",),
    )
    unstable = DetectedScreen(Page.FOREST_LOVE_PLANT, unstable_observation)
    stable = DetectedScreen(Page.FOREST_LOVE_PLANT, _observation())
    executor = ActionExecutor(
        _Device(),
        _Collector(after),
        _Detector(after, [unstable, stable]),
        _Logger(),
        None,
        "com.eg.android.AlipayGphone",
        settle_seconds=0.0,
    )

    result, observed = executor.execute(
        screen,
        Action("open-love-plant", ActionKind.TAP, "love_plant"),
        expected_pages=(Page.FOREST_LOVE_PLANT,),
    )

    assert result.status is ActionStatus.EXECUTED
    assert observed is stable


def test_changed_activity_rejects_stale_coordinates_before_touch():
    screen, after = _screen(())
    device = _Device(activity="OtherActivity")
    executor = ActionExecutor(
        device,
        _Collector(after),
        _Detector(after),
        _Logger(),
        None,
        "com.eg.android.AlipayGphone",
        settle_seconds=0.0,
    )

    result, observed = executor.execute(
        screen,
        Action("open-love-plant", ActionKind.TAP, "love_plant"),
    )

    assert result.status is ActionStatus.REJECTED
    assert result.point is None
    assert "Activity changed" in (result.error or "")
    assert observed is None
    assert device.taps == []


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


def test_animated_friend_page_allows_only_safe_advance_swipe():
    observation = replace(
        _observation(),
        errors=("unstable_observation:page changed during capture",),
    )
    friend = DetectedScreen(Page.FOREST_FRIEND, observation)
    after_observation = replace(
        _observation(),
        errors=("unstable_observation:friend transition",),
    )
    after = DetectedScreen(Page.FOREST_FRIEND, after_observation)
    executor = _executor(friend, after)

    result, observed = executor.execute(
        friend,
        Action(
            "forest-next-friend",
            ActionKind.SWIPE,
            start=(720, 2432),
            end=(720, 960),
            duration_ms=450,
        ),
        expected_pages=(
            Page.FOREST_FRIEND,
            Page.FOREST_TREASURE,
            Page.FOREST_HOME,
        ),
    )

    assert result.status is ActionStatus.EXECUTED
    assert observed is after
    assert executor.device.swipes == [((720, 2432), (720, 960), 450)]


def test_find_energy_accepts_identified_but_animating_first_friend():
    screen, _after = _screen(())
    screen = DetectedScreen(
        Page.FOREST_HOME,
        screen.observation,
        {"find_energy": Element("find_energy", Bounds(1100, 1800, 1400, 2200), screen.observation.id)},
    )
    friend_observation = replace(
        _observation(),
        errors=("unstable_observation:friend transition",),
    )
    friend = DetectedScreen(Page.FOREST_FRIEND, friend_observation)
    executor = ActionExecutor(
        _Device(),
        _Collector(friend),
        _Detector(friend),
        _Logger(),
        None,
        "com.eg.android.AlipayGphone",
        settle_seconds=0.0,
    )

    result, observed = executor.execute(
        screen,
        Action("forest-find-energy", ActionKind.TAP, "find_energy"),
        expected_pages=(Page.FOREST_FRIEND, Page.FOREST_TREASURE, Page.FOREST_HOME),
    )

    assert result.status is ActionStatus.EXECUTED
    assert observed is friend
