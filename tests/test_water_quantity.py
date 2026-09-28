"""The love watering quantity loop: one reading capture per increment.

Device cadence (2026-09-28): the pre-optimization loop re-observed before
every reading AND tap() observed again before every +10, so setting 100g
burned two extra ~3.4s captures per increment. The frame the tap confirms
already carries the next reading, so it feeds the next iteration and
tap_element() needs no before-frame of its own; only a + control missing
from that frame earns a refresh capture.
"""
from types import SimpleNamespace

import pytest

from domain_data import AutomationError, Element, Observation
from workflow.forest.daily import Forest


def home():
    # The label sits inside PLAZA_ENTRY (y .828), so no entrance scroll.
    return Observation(
        "home", 0.0, 1440, 3200, "alipay",
        [Element("真爱合种", (617, 2629, 782, 2674), "home"),
         Element("森林广场", (100, 400, 300, 460), "home")],
        page="forest",
    )


def page(oid, texts, love=True):
    return Observation(
        oid, 0.0, 1440, 3200, "alipay",
        [Element(text, (100, 400 + index * 90, 480, 460 + index * 90), oid)
         for index, text in enumerate(texts)],
        page="love" if love else "forest",
    )


def quantity(oid, value, plus=True):
    # The quantity sits inside WATER_DIALOG (x .48-.58, y .47-.49) while the
    # team total stays above the dialog band so the reading find stays unique.
    elements = [Element(value, (700, 1500, 830, 1560), oid),
                Element("42800g", (700, 1000, 900, 1060), oid)]
    if plus:
        elements.append(Element("+", (980, 1500, 1040, 1560), oid))
    return Observation(oid, 0.0, 1440, 3200, "alipay", elements, page="love")


class Store:
    def unresolved(self, _task):
        return None

    def verified_status(self, _task):
        return None


class QuantitySession:
    def __init__(self, frames):
        self.frames = iter(frames)
        self.observed = []
        self.taps = []
        self.elements = []
        self.done_calls = 0
        self.backs = []
        self.task = "forest.love"
        self.ex = SimpleNamespace(store=Store())

    def ensure(self, _page):
        return next(self.frames)

    def observe(self, reason):
        self.observed.append(reason)
        return next(self.frames)

    def tap(self, pattern, predicate, **kwargs):
        frame = next(self.frames)
        assert predicate(frame), pattern
        self.taps.append((pattern, kwargs))
        return frame

    def tap_element(self, obs, element, predicate, **kwargs):
        frame = next(self.frames)
        assert predicate(frame), kwargs["name"]
        self.elements.append((obs.id, element.text, kwargs["name"]))
        return frame

    def done(self, obs=None, **kwargs):
        self.done_calls += 1

    def back(self, target, **_kwargs):
        self.backs.append(target)


def dialog_open(oid):
    return page(oid, ["为爱攒能量", "42800g"])


def running_session():
    # home -> entry tap -> progress check -> dialog open -> reading frames.
    return QuantitySession([
        home(),
        page("b", ["为爱攒能量", "你当前有 22789 g"]),
        page("c", ["为爱攒能量", "你当前有 22789 g"]),
        dialog_open("d"),
        quantity("e", "20g"),
        quantity("f0", "30g"),
        quantity("f1", "40g"),
        quantity("f2", "50g"),
        quantity("f3", "60g"),
        quantity("f4", "70g"),
        quantity("f5", "80g"),
        quantity("f6", "90g"),
        quantity("f7", "100g"),
        page("g", ["已为爱攒100g"]),
    ])


def test_quantity_loop_reuses_each_confirm_frame_as_the_next_reading():
    session = running_session()

    Forest(session).water(True)

    # The single pre-loop capture is the whole observation budget: no
    # per-increment reading capture, no tap before-frame, no refresh.
    assert session.observed == ["water-progress", "water-quantity"]
    assert len(session.elements) == 8
    assert [obs_id for obs_id, _, _ in session.elements] == [
        "e", "f0", "f1", "f2", "f3", "f4", "f5", "f6"]
    assert all(name == "water-quantity-plus" for _, _, name in session.elements)
    assert [pattern for pattern, _ in session.taps] == [
        "^真爱合种$", "为爱攒能量", "^攒能量$"]
    assert session.taps[2][1]["spend"] is True
    assert session.taps[2][1]["detail"] == {"grams": 100}
    assert session.done_calls == 1
    assert session.backs == [("forest",)]


def test_quantity_already_at_target_skips_the_increment_taps():
    session = QuantitySession([
        home(),
        page("b", ["为爱攒能量", "你当前有 22789 g"]),
        page("c", ["为爱攒能量", "你当前有 22789 g"]),
        dialog_open("d"),
        quantity("e", "100g"),
        page("g", ["已为爱攒100g"]),
    ])

    Forest(session).water(True)

    assert session.observed == ["water-progress", "water-quantity"]
    assert session.elements == []
    assert session.done_calls == 1


def test_missing_plus_control_earns_exactly_one_refresh_capture():
    session = QuantitySession([
        home(),
        page("b", ["为爱攒能量", "你当前有 22789 g"]),
        page("c", ["为爱攒能量", "你当前有 22789 g"]),
        dialog_open("d"),
        quantity("e", "20g", plus=False),
        quantity("e2", "20g"),
        quantity("f0", "30g"),
        quantity("f1", "40g"),
        quantity("f2", "50g"),
        quantity("f3", "60g"),
        quantity("f4", "70g"),
        quantity("f5", "80g"),
        quantity("f6", "90g"),
        quantity("f7", "100g"),
        page("g", ["已为爱攒100g"]),
    ])

    Forest(session).water(True)

    assert session.observed == [
        "water-progress", "water-quantity", "water-quantity-refresh"]
    # The tap targets the refreshed frame, not the capture that missed the +.
    assert session.elements[0][0] == "e2"
    assert len(session.elements) == 8


def test_plus_still_missing_after_refresh_fails_closed():
    session = QuantitySession([
        home(),
        page("b", ["为爱攒能量", "你当前有 22789 g"]),
        page("c", ["为爱攒能量", "你当前有 22789 g"]),
        dialog_open("d"),
        quantity("e", "20g", plus=False),
        quantity("e2", "20g", plus=False),
        quantity("e3", "20g", plus=False),
    ])

    with pytest.raises(AutomationError) as exc:
        Forest(session).water(True)

    assert exc.value.code == "AMBIGUOUS"
    assert session.observed == [
        "water-progress", "water-quantity",
        "water-quantity-refresh", "water-quantity-refresh"]
    assert session.done_calls == 0
