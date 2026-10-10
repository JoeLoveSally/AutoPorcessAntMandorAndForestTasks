"""A transient UNKNOWN pre-tap frame is re-observed instead of failing.

Device evidence (2026-10-10, run 33a71e): after Back landed on the alipay
home, the next pre-tap observation dropped the rule's group-one anchor
扫一扫 for a single frame (the banner was rotating its search keyword) so
classify flipped a perfectly familiar surface to UNKNOWN - while the tap
target 蚂蚁庄园 was visibly on screen. session.tap handed that frame to
ex.tap, validate refused with "Cannot act on unknown page", and the task
died without ever sending a touch.

The refresh is bounded: a persistent UNKNOWN still reaches the executor,
where validate fails closed - tolerance must not become a blind-act loop.
"""

from types import SimpleNamespace

from domain_data import Element, Observation
from workflow.session import Session


def observation(oid, texts, *, page):
    elements = [Element(text, bounds, oid) for text, bounds in texts]
    return Observation(oid, 0.0, 1440, 3200, "alipay", elements, page)


class TappingExecutor:
    def __init__(self, captures, taps):
        self._captures = iter(captures)
        self.observer = SimpleNamespace(capture=lambda _reason: next(self._captures))
        self.budget = SimpleNamespace(check=lambda: None)
        self._taps = iter(taps)
        self.tap_calls = []

    def tap(self, obs, element, predicate, name, task, **_kwargs):
        self.tap_calls.append((obs.id, element.text))
        return next(self._taps)


def test_pattern_tap_rides_out_a_transient_unknown_frame():
    flake = observation("1", [("蚂蚁庄园", (380, 1280, 500, 1370))],
                        page="UNKNOWN")
    known = observation("2", [("蚂蚁庄园", (380, 1280, 500, 1370))],
                        page="alipay")
    landed = observation("3", [("饲料任务", (0, 0, 100, 100))], page="feed")
    executor = TappingExecutor(captures=[flake, known], taps=[landed])
    session = Session(executor, {"package": "alipay"})

    result = session.tap("^蚂蚁庄园$", lambda o: o.page == "feed")

    assert result is landed
    # The tap rode the refresh: it fired from the re-observed frame, not the
    # UNKNOWN one validate would have refused.
    assert executor.tap_calls == [("2", "蚂蚁庄园")]


def test_pattern_tap_stops_refreshing_a_persistent_unknown():
    frames = [observation(str(i), [("蚂蚁庄园", (380, 1280, 500, 1370))],
                          page="UNKNOWN") for i in (1, 2, 3)]
    landed = observation("4", [("饲料任务", (0, 0, 100, 100))], page="feed")
    executor = TappingExecutor(captures=frames, taps=[landed])
    session = Session(executor, {"package": "alipay"})

    session.tap("^蚂蚁庄园$", lambda o: o.page == "feed")

    # Exactly two re-observations (1 -> 2 -> 3), then the third UNKNOWN
    # frame goes to the executor, whose validate still refuses it - the
    # refresh bounds the wait, it does not swallow the fail-closed gate.
    assert executor.tap_calls == [("3", "蚂蚁庄园")]


def test_known_frames_skip_the_refresh():
    known = observation("1", [("蚂蚁庄园", (380, 1280, 500, 1370))],
                        page="alipay")
    landed = observation("2", [("饲料任务", (0, 0, 100, 100))], page="feed")
    executor = TappingExecutor(captures=[known], taps=[landed])
    session = Session(executor, {"package": "alipay"})

    session.tap("^蚂蚁庄园$", lambda o: o.page == "feed")

    assert executor.tap_calls == [("1", "蚂蚁庄园")]
