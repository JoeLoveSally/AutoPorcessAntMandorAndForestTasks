"""Farm flow ordering calibrated against device evidence.

Run 9d8f76 (2026-09-25): the farm home's 施肥 was OCR'd on the farm-open
frame (0012), gone from 0013's transition frame and the 做任务集肥料 drawer
was open at 0014 - spec L67's auto-jump lands a beat after the home renders.
The old immediate farm_tasks check therefore ran pre-jump, and ^施肥$'s
refresh loop refused to act across the page change (found 0). The flow must
wait for the spec-guaranteed jump before claiming the drawer rows.
"""

import pytest

from domain_data import Element, Observation
from workflow.manor.daily import Manor


def observation(oid, texts, page):
    return Observation(
        oid, 0.0, 1440, 3200, "alipay",
        [Element(text, (100, 400 + index * 100, 900, 470 + index * 100), oid)
         for index, text in enumerate(texts)],
        page=page,
    )


class Stop(Exception):
    pass


class FarmSession:
    def __init__(self):
        self.task = "manor.feed.farm"
        self.absent = set()
        self.home = observation("home", ["支付宝·芭芭农场", "施肥", "肥料"],
                                "farm")
        self.drawer = observation("drawer", ["做任务集肥料", "每日签到",
                                             "蚂蚁庄园小鸡肥料"], "farm_tasks")
        self.claimed = observation("claimed", ["做任务集肥料", "每日签到",
                                               "已领取", "蚂蚁庄园小鸡肥料"],
                                   "farm_tasks")
        self.obs = self.home
        self.wait_calls = []
        self.row_calls = []
        self.claim_taps = 0
        self.backs = []
        self.drawer_closed = False

    def row(self, title, required=True, reset=False, page="feed"):
        self.row_calls.append(title)
        if title in self.absent:
            return self.obs, None, None
        text = "去完成" if title == "^去芭芭农场" else "领取"
        anchor = Element(title, (100, 400, 900, 470), "row")
        button = Element(text, (1150, 900, 1350, 970), "row")
        return self.obs, anchor, button

    def tap_element(self, obs, button, predicate, **kwargs):
        name = kwargs.get("name")
        if name == "farm-open":
            assert predicate(self.home)
            self.obs = self.home
        elif name == "fertilizer-claim":
            assert predicate(self.claimed)
            self.claim_taps += 1
        elif name == "drawer-close":
            # Device evidence (2026-09-29, run 5742c4): the drawer exits via
            # its top-right X, never via Back - Back left the whole
            # container and landed on feed, starving back(("farm",)).
            assert button.text == "关闭做任务集肥料"
            assert predicate(self.home)
            self.drawer_closed = True
            self.obs = self.home
        else:
            raise AssertionError(f"unexpected tap_element {name}")

    def wait(self, predicate, reason="wait", timeout=None):
        self.wait_calls.append(reason)
        assert predicate(self.drawer)
        self.obs = self.drawer
        return self.obs

    def back(self, target, **kwargs):
        self.backs.append(target)
        self.obs = self.home
        raise Stop

    def tap(self, pattern, predicate, **kwargs):
        # Reaching 施肥 means the claims and the X close all ran in order;
        # the fertilization stage itself stays out of this unit's scope.
        assert pattern == "^施肥$"
        raise Stop


def test_farm_waits_for_the_spec_auto_jump_before_drawer_claims():
    session = FarmSession()

    with pytest.raises(Stop):
        Manor(session).farm()

    assert session.wait_calls == ["farm-jump"]
    assert session.row_calls == ["^去芭芭农场", "蚂蚁庄园小鸡肥料", "每日签到"]
    assert session.claim_taps == 2
    assert session.drawer_closed is True
    assert session.backs == []


def test_absent_sign_row_is_skipped_and_the_durable_claim_still_fires():
    # Device evidence (2026-09-28, run 77dae5): the welcome card's
    # countdown auto-claimed the sign before the jump, and the drawer then
    # rendered no 每日签到 row at all across 34 frames - the loop must skip
    # it (required=False + the None guard) and still claim the manure row
    # that IS there with its 领取 pill.
    session = FarmSession()
    session.absent = {"每日签到"}

    with pytest.raises(Stop):
        Manor(session).farm()

    assert session.row_calls == ["^去芭芭农场", "蚂蚁庄园小鸡肥料", "每日签到"]
    assert session.claim_taps == 1
    assert session.drawer_closed is True
    assert session.backs == []
