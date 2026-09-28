"""Energy-rain gift panel dead-button fallback.

Device evidence (2026-09-27, run c59b7f): the round-one result panel shows
three same-text 送TA机会 buttons (the tutorial hand covers the leftmost one,
which OCRs as bare 送T); min-by-(y,x) tapped the middle button and it sat
dead for the whole wait while the pixel-identical right button had answered
the day before (run 06fb5b, point (936,1807)). The friend row rotates
daily, so the walk must try the candidates, cancel a tap whose panel never
answered, and fail closed once every button is spent.
"""

from types import SimpleNamespace

import pytest

from domain_data import AutomationError, Element, Observation
from workflow.forest import energy_rain
from workflow.forest.daily import Forest


def frame(oid, page, pairs):
    return Observation(oid, 0.0, 1440, 3200, "alipay",
                       [Element(text, bounds, oid) for text, bounds in pairs], page)


def gift_panel(oid):
    return frame(oid, "rain", [
        ("恭喜获得", (617, 824, 826, 883)),
        ("送好友机会，再来一场能量雨", (387, 1369, 1055, 1417)),
        ("送T", (290, 1785, 388, 1830)),          # leftmost, hand-occluded
        ("送TA机会", (573, 1783, 737, 1832)),       # middle, dead on 09-27
        ("送TA机会", (855, 1783, 1018, 1832)),      # right, answered on 09-26
    ])


class Store:
    def __init__(self):
        self.pending = None
        self.actions = []

    def unresolved(self, _task):
        return self.pending is not None

    def pending_frames(self, _task):
        return [self.pending] if self.pending else []

    def action(self, action_id, status, frame_id):
        self.actions.append((action_id, status, frame_id))


class RainSession:
    def __init__(self, dead):
        self.task = "forest.rain"
        self.ex = SimpleNamespace(store=Store())
        self.dead = dead
        self.attempts = 0
        self.taps = []
        self.plays = []
        self.done_calls = 0
        self.back_calls = []

    def ensure(self, _target):
        return frame("home", "forest", [("能量雨", (180, 1400, 300, 1460))])

    def scroll(self, _region, **_kwargs):
        raise AssertionError("the rain entry is already on the plaza frame")

    def tap(self, pattern, predicate, **_kwargs):
        start = frame("start", "rain",
                      [("天天能量雨", (500, 300, 940, 380)),
                       ("立即开启", (520, 2600, 920, 2720))])
        assert pattern and predicate(start)
        return start

    def observe(self, name):
        if name == "rain-start":
            return frame("start", "rain",
                         [("天天能量雨", (500, 300, 940, 380)),
                          ("立即开启", (520, 2600, 920, 2720))])
        if name == "rain-gift":
            return gift_panel("gift")
        if name == "rain-gift-retry":
            return gift_panel("retry")
        raise AssertionError(f"unexpected observation {name}")

    def tap_element(self, _obs, element, _predicate, **kwargs):
        self.taps.append((element.point, kwargs.get("name")))
        self.attempts += 1
        if self.attempts <= self.dead:
            # The intent fires and the wait starves: exactly the real
            # executor's RESULT_UNKNOWN state for this spend.
            self.ex.store.pending = (f"a{self.attempts}", "rain-gift",
                                     "before", self.task)
            raise AutomationError("panel never answered", "TIMEOUT")

    def done(self, *_args, **_kwargs):
        self.done_calls += 1

    def back(self, target, **kwargs):
        self.back_calls.append((target, kwargs))


def test_dead_gift_button_cancels_and_walks_right_to_left(monkeypatch):
    session = RainSession(dead=1)
    monkeypatch.setattr(
        energy_rain, "play",
        lambda _s, round_no: session.plays.append(round_no))

    Forest(session).rain()

    # Rightmost candidate first (the button that answered on 09-26); the
    # dead middle tap is cancelled on the affordance that never went away,
    # then the next button sends.
    assert session.taps == [((936, 1807), "rain-gift"),
                            ((655, 1807), "rain-gift")]
    assert session.ex.store.actions == [("a1", "CANCELLED", "retry")]
    assert session.plays == [1, 2]
    assert session.done_calls == 1
    assert session.back_calls == [(("forest",), {})]


def test_every_dead_gift_button_fails_closed(monkeypatch):
    session = RainSession(dead=2)
    monkeypatch.setattr(
        energy_rain, "play",
        lambda _s, round_no: session.plays.append(round_no))

    with pytest.raises(AutomationError) as raised:
        Forest(session).rain()

    assert raised.value.code == "TIMEOUT"
    assert session.taps == [((936, 1807), "rain-gift"),
                            ((655, 1807), "rain-gift")]
    assert [(action[0], action[1]) for action in session.ex.store.actions] == [
        ("a1", "CANCELLED"), ("a2", "CANCELLED")]
    assert session.plays == [1]      # round two must never start
    assert session.done_calls == 0
