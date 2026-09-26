"""Daily sign-in strip behaviour derived from 2026-09-21 device evidence.

The strip carries no standalone "签到" text, OCR misreads "今天" often, and
the whole strip disappears once claimed, so the flow anchors on the list
header plus a "第N天" cell instead.
"""

import pytest

from domain_data import AutomationError, Element, Observation
from workflow.manor.daily import Manor

# Normalized anchors: header (.42, .30) in (.2, .24, .8, .40); cells and the
# claim control share the strip band y in (.36, .48).
BOUNDING_BOXES = {
    "饲料任务": (400, 900, 800, 1000),
    "第2天": (200, 1200, 400, 1300),
    "第3天": (200, 1200, 400, 1300),
    "领取": (1050, 1200, 1250, 1300),
    "已领取": (1050, 1200, 1250, 1300),
    # Zero-headroom refusal dialog (2026-09-24 device bounds, run 0ace75).
    "先消耗一些饲料再来领取吧~": (427, 1635, 1017, 1682),
    "知道了": (877, 1846, 1031, 1908),
    # Near-full confirm dialog (2026-09-25 device bounds, run 7ecb00).
    "饲料袋快满了": (536, 1482, 898, 1541),
    "现在饲料袋只能装下60g，确认领取吗？": (321, 1637, 1096, 1683),
    "去帮好友喂食": (327, 1856, 638, 1911),
    "确认": (908, 1853, 1020, 1912),
}


def feed(oid, texts=(), overlays=None):
    elements = [Element(text, BOUNDING_BOXES[text], oid) for text in texts]
    return Observation(oid, 0.0, 1440, 3200, "alipay", elements, "feed", overlays or [])


class FakeSession:
    def __init__(self, *, ensure, observes=(), tap_element_results=(), tap_results=()):
        self.config = {}
        self._ensure = ensure
        self._observes = list(observes)
        self._tap_element_results = list(tap_element_results)
        self._tap_results = list(tap_results)
        self.tap_element_calls = []
        self.tap_calls = []
        self.scroll_count = 0
        self.done_args = []
        self.obs = None

    def ensure(self, _page):
        return self._ensure

    def scroll(self, *args, **kwargs):
        self.scroll_count += 1
        raise AssertionError("the feed top must be visible without scrolling")

    def observe(self, _reason):
        return self._observes.pop(0)

    def tap_element(self, obs, element, predicate, **kwargs):
        self.tap_element_calls.append((element.text, kwargs))
        after = self._tap_element_results.pop(0)
        if not predicate(after):
            raise AssertionError("postcondition must hold on the scripted result")
        self.obs = after
        return after

    def tap(self, pattern, predicate, **kwargs):
        self.tap_calls.append((pattern, kwargs))
        after = self._tap_results.pop(0)
        if not predicate(after):
            raise AssertionError(f"postcondition must hold for {pattern}")
        self.obs = after
        return after

    def done(self, _obs=None, **kwargs):
        self.done_args.append(kwargs)


def test_claimable_sign_strip_is_claimed_and_verified():
    before = feed("1", ["饲料任务", "第2天", "领取"])
    after = feed("2", ["饲料任务", "第2天", "已领取"])
    verify = feed("3", ["饲料任务", "第2天", "已领取"])
    session = FakeSession(
        ensure=before, tap_element_results=[after], observes=[verify],
    )

    Manor(session).sign()

    assert [call[0] for call in session.tap_element_calls] == ["领取"]
    assert session.tap_element_calls[0][1]["name"] == "daily-sign"
    assert session.tap_calls == []
    assert session.done_args == [{}]


def test_missing_sign_strip_is_confirmed_absent_after_two_observations():
    top = feed("1", ["饲料任务"])
    confirm_1 = feed("2", ["饲料任务"])
    confirm_2 = feed("3", ["饲料任务"])
    session = FakeSession(ensure=top, observes=[confirm_1, confirm_2])

    Manor(session).sign()

    assert session.tap_element_calls == []
    assert session.done_args == [{"already": True}]


def test_claimed_strip_is_not_tapped_again():
    before = feed("1", ["饲料任务", "第3天", "已领取"])
    session = FakeSession(ensure=before)

    Manor(session).sign()

    assert session.tap_element_calls == []
    assert session.done_args == [{"already": True}]


def test_sign_overflow_confirmation_is_required_before_verification():
    before = feed("1", ["饲料任务", "第2天", "领取"])
    overflow = feed("2", ["饲料任务", "第2天"], overlays=["overflow"])
    confirmed = feed("3", ["饲料任务", "第2天"])
    verify = feed("4", ["饲料任务", "第2天", "已领取"])
    session = FakeSession(
        ensure=before,
        tap_element_results=[overflow],
        tap_results=[confirmed],
        observes=[verify],
    )

    Manor(session).sign()

    assert [call[0] for call in session.tap_calls] == ["^确认$|^继续领取$"]
    assert session.tap_calls[0][1]["spend"] is True
    assert session.done_args == [{}]


def test_sign_success_requires_a_fresh_receipt_observation():
    before = feed("1", ["饲料任务", "第2天", "领取"])
    overflow = feed("2", ["饲料任务", "第2天"], overlays=["overflow"])
    confirmed = feed("3", ["饲料任务", "第2天"])
    verify = feed("4", ["饲料任务", "第2天", "领取"])
    session = FakeSession(
        ensure=before,
        tap_element_results=[overflow],
        tap_results=[confirmed],
        observes=[verify],
    )

    with pytest.raises(AutomationError, match="not verified"):
        Manor(session).sign()

    assert session.done_args == []


def test_full_bag_refusal_is_dismissed_and_reports_missing_prerequisite():
    # Device evidence (2026-09-24, run 0ace75): at the 1800g cap the claim
    # dialog refuses outright (饲料袋已满; 知道了 / 去帮好友喂食) and spec
    # L29's discard-confirm never appears, so tapping for 确认|继续领取
    # fails with "found 0". Dismiss via 知道了 and report the missing
    # prerequisite (family.feed spends 180g) instead.
    before = feed("1", ["饲料任务", "第2天", "领取"])
    refused = feed("2", ["饲料任务", "第2天", "先消耗一些饲料再来领取吧~", "知道了"],
                   overlays=["overflow"])
    dismissed = feed("3", ["饲料任务", "第2天"])
    session = FakeSession(
        ensure=before,
        tap_element_results=[refused],
        tap_results=[dismissed],
    )

    with pytest.raises(AutomationError, match="Feed bag full") as exc:
        Manor(session).sign()

    assert [call[0] for call in session.tap_calls] == ["^知道了$"]
    assert exc.value.code == "BLOCKED"
    assert session.done_args == []


def test_near_full_bag_confirm_is_tapped_per_spec_l29():
    # Device evidence (2026-09-25, run 7ecb00): with 60g of headroom the
    # claim pops 饲料袋快满了 / 现在饲料袋只能装下60g，确认领取吗？ with
    # 去帮好友喂食 + 确认. That 去帮好友喂食 collides with the old
    # hard-refusal key (would hunt 知道了 and fail found 0), so the branch
    # keys on 先消耗/知道了 instead; spec L29 then mandates 确认. The frame
    # reads UNKNOWN behind the dialog and may linger a capture after the
    # tap, hence allow_unknown + recover=False.
    before = feed("1", ["饲料任务", "第2天", "领取"])
    almost = feed("2", ["饲料任务", "第2天", "饲料袋快满了",
                        "现在饲料袋只能装下60g，确认领取吗？", "去帮好友喂食", "确认"],
                  overlays=["overflow"])
    confirmed = feed("3", ["饲料任务", "第2天"])
    verify = feed("4", ["饲料任务", "第2天", "已领取"])
    session = FakeSession(
        ensure=before,
        tap_element_results=[almost],
        tap_results=[confirmed],
        observes=[verify],
    )

    Manor(session).sign()

    # Anchored: the dialog body 现在饲料袋只能装下60g，确认领取吗？ also
    # contains 确认 (run e5bb6b found 2 unanchored).
    assert [call[0] for call in session.tap_calls] == ["^确认$|^继续领取$"]
    assert session.tap_calls[0][1]["allow_unknown"] is True
    assert session.tap_calls[0][1]["recover"] is False
    assert session.tap_calls[0][1]["spend"] is True
    assert session.done_args == [{}]
