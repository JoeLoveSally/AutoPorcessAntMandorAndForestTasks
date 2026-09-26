"""Donation flow anchors calibrated against 2026-09-24 device labels.

Device evidence (run 17b8ff): the project row and the detail page's
bottom-center control both read 去捐蛋, while spec L14 describes the
detail action as 立即捐蛋 - every tap anchor must accept the real label
or the flow dies with "found 0" right after page recognition succeeds.
"""

import re
from types import SimpleNamespace

import pytest

from domain_data import AutomationError, Element, Observation
from workflow.manor.daily import Manor
from workflow.session import Session


def obs(page, texts=()):
    elements = [Element(text, (100, 2000, 700, 2060), "fixture") for text in texts]
    return Observation("fixture", 0.0, 1440, 3200, "alipay", elements, page)


def quantity_frame():
    # Quantity controls must sit in region (0, .5, 1, 1) for the flow's
    # one-egg verification (y 2000-2060 -> cy .63).
    return obs("donate_quantity", ["1颗", "5颗", "自定义", "当前还有8颗爱心蛋"])


class FakeSession:
    def __init__(self):
        self.task = "manor.family.donate_egg"
        self.ex = SimpleNamespace(store=SimpleNamespace(unresolved=lambda _task: False))
        self._row_obs = obs("family_tasks")
        self._tap_element_results = [
            obs("donate_projects"),
            obs("donate_detail", ["活动截止时间", "筹集中", "爱心值奖励", "去捐蛋"]),
        ]
        self._observes = [
            obs("donate_projects", ["去捐蛋"]),
            quantity_frame(),
        ]
        self._tap_results = [quantity_frame(), obs("donate_success")]
        self._ensure = self._row_obs
        self.tap_element_calls = []
        self.tap_calls = []
        self.observe_calls = []
        self.ensure_calls = []
        self.complete_row_calls = []
        self.obs = None

    def row(self, _pattern, page="feed"):
        assert page == "family_tasks"
        title = Element("每日捐蛋做好事(0/1)", (100, 1000, 700, 1060), "fixture")
        button = Element("去捐蛋", (1000, 1900, 1300, 1990), "fixture")
        return self._row_obs, title, button

    def tap_element(self, _obs, element, predicate, **kwargs):
        self.tap_element_calls.append((element.text, kwargs))
        after = self._tap_element_results.pop(0)
        assert predicate(after), "postcondition must hold on the scripted result"
        self.obs = after
        return after

    def observe(self, reason):
        self.observe_calls.append(reason)
        after = self._observes.pop(0)
        self.obs = after
        return after

    def tap(self, pattern, predicate, **kwargs):
        self.tap_calls.append((pattern, kwargs))
        after = self._tap_results.pop(0)
        assert predicate(after), "postcondition must hold on the scripted result"
        self.obs = after
        return after

    def ensure(self, page):
        self.ensure_calls.append(page)
        return self._ensure

    def complete_row(self, pattern, page="feed"):
        self.complete_row_calls.append((pattern, page))


def test_donation_walks_projects_detail_quantity_with_device_labels():
    session = FakeSession()

    Manor(session).family_donate()

    assert [call[1]["name"] for call in session.tap_element_calls] == [
        "open-donation", "first-project"]
    # The detail page's real bottom label must match the tap anchor.
    assert re.fullmatch(session.tap_calls[0][0], "去捐蛋")
    assert session.tap_calls[1][1]["spend"] is True
    assert session.tap_calls[1][1]["detail"] == {"eggs": 1}
    assert session.observe_calls == ["project-list", "donation-quantity"]
    assert session.ensure_calls == ["family_tasks"]
    assert session.complete_row_calls == [("每日捐蛋|捐蛋做好事", "family_tasks")]


def test_complete_row_accepts_the_done_title_when_ocr_missed_the_side_button():
    # Device evidence (2026-09-24, run ed9ed9): the freshly completed
    # donation row sat at the list bottom; OCR returned only the title
    # 每日捐蛋做好事(1/1), so row() returned the title itself as the row
    # button (its (1/1) guarantee), and complete_row rejected it because
    # the marker set only listed side-button labels like 明天再来.
    obs = Observation("done", 0.0, 1440, 3200, "alipay", [], "family_tasks")
    anchor = Element("每日捐蛋做好事(1/1)", (100, 3132, 700, 3190), "done")
    session = Session(SimpleNamespace(), {"package": "alipay"})
    session.row = lambda *_args, **_kwargs: (obs, anchor, anchor)
    session.done = lambda *_args, **_kwargs: None

    session.complete_row("每日捐蛋|捐蛋做好事", page="family_tasks")

    # A pending row still fails closed on its side button.
    pending = Element("去捐蛋", (1000, 3132, 1300, 3190), "done")
    session.row = lambda *_args, **_kwargs: (obs, anchor, pending)
    with pytest.raises(AutomationError, match="Task completion not verified"):
        session.complete_row("每日捐蛋|捐蛋做好事", page="family_tasks")
