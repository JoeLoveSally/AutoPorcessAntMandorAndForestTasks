"""Farm flow ordering calibrated against device evidence.

Run 9d8f76 (2026-09-25): the farm home's 施肥 was OCR'd on the farm-open
frame (0012), gone from 0013's transition frame and the 做任务集肥料 drawer
was open at 0014 - spec L67's auto-jump lands a beat after the home renders.
The old immediate farm_tasks check therefore ran pre-jump, and ^施肥$'s
refresh loop refused to act across the page change (found 0). The flow must
wait for the spec-guaranteed jump before claiming the drawer rows.
"""

import pytest

from domain_data import AutomationError, Element, Observation
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


class FarmExecutor:
    """Executor stub for recovery's close-circle branch (run f427d5)."""

    def __init__(self, session):
        self.session = session
        self.closes = []

    def tap(self, obs, element, predicate, name, task, **kwargs):
        assert element.text == "广告关闭"
        assert name == "close-farm-gift"
        assert kwargs.get("allow_overlay") is True
        # The close must satisfy recovery's overlay-removal predicate on
        # the farm home underneath - Android Back would have left the
        # whole 芭芭农场 container for feed instead.
        assert predicate(self.session.home)
        self.closes.append(name)
        self.session.obs = self.session.home
        return self.session.home


class FarmSession:
    def __init__(self, tail=False):
        self.task = "manor.feed.farm"
        self.absent = set()
        self.home = observation("home", ["支付宝·芭芭农场", "施肥", "肥料"],
                                "farm")
        self.drawer = observation("drawer", ["做任务集肥料", "每日签到",
                                             "蚂蚁庄园小鸡肥料"], "farm_tasks")
        self.claimed = observation("claimed", ["做任务集肥料", "每日签到",
                                               "已领取", "蚂蚁庄园小鸡肥料"],
                                   "farm_tasks")
        self.fert_prompt = observation("fert-prompt", ["支付宝·芭芭农场",
                                                       "施肥", "主即领肥"],
                                       "farm")
        self.popup_pending = observation(
            "popup-pending", ["支付宝·芭芭农场", "丰收礼包待领取", "肥料",
                              "立即领取"], "farm")
        self.popup_claimed = observation(
            "popup-claimed", ["支付宝·芭芭农场", "半收礼包已领取", "肥料",
                              "点此逛一逛再赚1000肥料>"], "farm")
        # The vision rule classifies the popup as farm_gift with its
        # bottom-center close circle (device 2026-09-30, run f427d5).
        for popup in (self.popup_pending, self.popup_claimed):
            popup.overlays.append("farm_gift")
            popup.elements.append(
                Element("广告关闭", (660, 2261, 780, 2381), popup.id))
        self.obs = self.home
        self.tail = tail
        self.fertilizations = 0
        self.claim_rides_overlay = False
        self.ex = FarmExecutor(self)
        self.wait_calls = []
        self.row_calls = []
        self.claim_taps = 0
        self.backs = []
        self.drawer_closed = False

    def observe(self, reason="observe"):
        return self.obs

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
        if not self.tail:
            # Reaching 施肥 means the claims and the X close all ran in
            # order; the fertilization stage itself stays out of this
            # unit's scope.
            assert pattern == "^施肥$"
            raise Stop
        if pattern == "^施肥$":
            if self.fertilizations:
                # Round 2 only re-runs what round 1 already proved.
                raise Stop
            assert predicate(self.fert_prompt)
            self.fertilizations += 1
            self.obs = self.fert_prompt
        elif pattern == "[立三主]即领肥":
            assert predicate(self.popup_pending)
            self.obs = self.popup_pending
        elif pattern == "[立三主]即领取":
            # The popup is classified farm_gift: without riding the
            # overlay through, session.tap would dismiss it before
            # targeting and never find the claim CTA.
            if not kwargs.get("overlay"):
                raise AssertionError("claim tap must allow the overlay")
            self.claim_rides_overlay = True
            assert predicate(self.popup_claimed)
            self.obs = self.popup_claimed
        else:
            raise AssertionError(f"unexpected tap {pattern}")
        return self.obs


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


def test_fertilize_tail_claims_through_the_overlay_and_closes_its_circle():
    # Device evidence (2026-09-30, run f427d5): the first fertilize round
    # claimed 600肥料 and then one Android Back from the 丰收礼包 popup
    # left the whole 芭芭农场 container for feed (spec L67 closes it with
    # the popup's X), starving back(("farm",)). The claim must ride the
    # classified overlay through (session.tap dismisses overlays before
    # targeting) and the exit must be recovery's close circle - the tail
    # must never press Android Back.
    session = FarmSession(tail=True)

    with pytest.raises(Stop):
        Manor(session).farm()

    assert session.drawer_closed is True
    assert session.claim_rides_overlay is True
    assert session.ex.closes == ["close-farm-gift"]
    assert session.backs == []


class BindingGateSession:
    """The 芭芭农场 mini-program's Taobao-binding landing page (run 9282ac)."""

    def __init__(self, claimable=True):
        self.task = "manor.feed.farm"
        self.gate = observation(
            "gate", ["支付宝·芭芭农场", "种果树得水果", "1分钱领一箱水果",
                     "去绑定淘宝账号"], "UNKNOWN")
        self.feed = observation("feed", ["蚂蚁庄园", "去芭芭农场"], "feed")
        self.obs = None
        self._rows = iter([
            (self.feed, Element("去芭芭农场", (300, 2400, 700, 2460), "feed"),
             Element("去完成", (1150, 2400, 1300, 2460), "feed")),
            (self.feed, Element("去芭芭农场", (300, 2400, 700, 2460), "feed"),
             Element("领取" if claimable else "去完成",
                     (1150, 2400, 1300, 2460), "feed")),
        ])
        self.done_args = []
        self.ensure_calls = []
        self.open_predicates = []

    def row(self, _pattern, reset=False, page="feed"):
        return next(self._rows)

    def tap_element(self, _obs, _element, predicate, **_kwargs):
        self.open_predicates.append(predicate)
        self.obs = self.gate
        return self.gate

    def ensure(self, page):
        self.ensure_calls.append(page)
        self.obs = self.feed
        return self.feed

    def done(self, _obs, **kwargs):
        self.done_args.append(kwargs)


def test_farm_accepts_the_binding_landing_and_finishes_on_a_claimable_card():
    # Device evidence (2026-10-09, run 9282ac): the 小号's 芭芭农场 opened on
    # its Taobao-binding landing page (page UNKNOWN, frames 0221-0228) and
    # held steady for the whole 25s page timeout, so the old farm-open
    # predicate failed closed and aborted the chain. The open still counted
    # as the daily browse - the next run (7ef332) read the parent card as
    # claimable (领取) - so the flow must accept the landing, route back to
    # the feed and finish on the claimable card.
    session = BindingGateSession()

    Manor(session).farm()

    assert session.open_predicates[0](session.gate)
    assert not session.open_predicates[0](session.feed)
    assert session.ensure_calls == ["feed"]
    assert session.done_args == [{"already": True}]


def test_farm_still_fails_closed_when_the_binding_page_leaves_the_card_pending():
    session = BindingGateSession(claimable=False)

    with pytest.raises(AutomationError, match="not claimable"):
        Manor(session).farm()

    assert session.ensure_calls == ["feed"]
    assert session.done_args == []
