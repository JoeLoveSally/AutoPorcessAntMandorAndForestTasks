"""Own-energy collection guards derived from the 2026-09-21 device failure.

The campaign modal hid the crown bubbles while the top-right total badge
"21563g" kept matching the naive bubble pattern, so the tap postcondition
could never hold and the run timed out.
"""

import pytest

from domain_data import AutomationError, Element, Observation
from workflow import recovery
from workflow.forest.daily import Forest

BADGE = (1155, 416, 1300, 487)      # top-right total, center (.85, .14)
CROWN = (666, 756, 810, 856)        # crown bubble, center (.51, .25)
CROWN_LOW = (300, 900, 460, 1010)   # drifted crown bubble, center (.26, .30)
PLAZA_CARD = (871, 2572, 965, 2624)  # plaza entry badge, center (.64, .81)
SIGN_BALL = (150, 560, 260, 660)    # delayed sign-in bubble, center (.14, .19)
SIGN_TEXT = (120, 720, 320, 800)    # "能量签到" under the sign-in bubble


def observation(oid, texts=(), page="forest", overlays=None):
    elements = [Element(text, bounds, oid) for text, bounds in texts]
    return Observation(oid, 0.0, 1440, 3200, "alipay", elements, page, overlays or [])


def test_total_badge_plaza_card_and_sign_bubble_are_not_collected_in_the_loop():
    obs = observation("1", [
        ("21563g", BADGE),      # naive ^\d+g$ matched this on 2026-09-21
        ("9999g", BADGE),       # even a short badge in the corner is no bubble
        ("150g", PLAZA_CARD),   # plaza entry badge below the crown band
        ("5g", SIGN_BALL),      # sign-in bubble belongs to its own reward flow
        ("能量签到", SIGN_TEXT),
        # Real-device evidence (2026-09-22): this text is the 神奇海洋
        # reminder pill below the crown - never a bubble, never a sign anchor.
        ("5g 能量", (511, 1217, 613, 1266)),
        ("105g", CROWN),
    ])

    assert [bubble.text for bubble in Forest._bubbles(obs)] == ["105g"]


def test_lone_numeric_text_in_crown_band_is_attempted():
    obs = observation("2", [("5g", CROWN)])

    assert [bubble.text for bubble in Forest._bubbles(obs)] == ["5g"]


class FakeSession:
    def __init__(self, *, ensure, stream=(), tap_timeouts=0, config=None,
                 reentries=()):
        self.config = config or {"energy_sign_wait": 0}
        self._ensure = ensure
        self._reentries = list(reentries)
        self._stream = list(stream)
        self._tap_timeouts = tap_timeouts
        self.observe_reasons = []
        self.taps = []
        self.done_args = []
        self.done_obs = None
        self.waits = []
        self.scrolls = []
        self.backs = []
        self.ensure_calls = 0
        self.obs = None

    def ensure(self, _page):
        self.ensure_calls += 1
        if self.ensure_calls == 1:
            return self._ensure
        if self._reentries:
            return self._reentries.pop(0)
        return self._ensure

    def observe(self, reason):
        self.observe_reasons.append(reason)
        return self._stream.pop(0)

    def tap_element(self, obs, element, predicate, **kwargs):
        self.taps.append((element.text, kwargs))
        if len(self.taps) <= self._tap_timeouts:
            raise AutomationError("Postcondition failed: collect-energy", "TIMEOUT")
        after = self._stream.pop(0)
        if not predicate(after):
            raise AssertionError("postcondition must hold on the scripted result")
        self.obs = after
        return after

    def tap(self, pattern, predicate, **kwargs):
        self.taps.append((pattern, kwargs))
        after = self._stream.pop(0)
        if not predicate(after):
            raise AssertionError(f"postcondition must hold for {pattern}")
        self.obs = after
        return after

    def wait(self, predicate, reason="wait", timeout=None):
        self.waits.append(reason)
        while self._stream:
            after = self._stream.pop(0)
            if predicate(after):
                self.obs = after
                return after
        raise AssertionError("wait predicate must hold on some scripted observation")

    def scroll(self, *args, **kwargs):
        self.scrolls.append(kwargs)
        after = self._stream.pop(0)
        target = kwargs.get("target")
        if target is not None and not target(after):
            raise AutomationError("Postcondition failed: swipe", "TIMEOUT")
        self.obs = after
        return after

    def back(self, target, allow_unknown=False):
        self.backs.append((target, allow_unknown))
        while self._stream:
            after = self._stream.pop(0)
            if target(after):
                self.obs = after
                return after
        raise AssertionError("back predicate must hold on some scripted observation")

    def done(self, obs=None, **kwargs):
        self.done_obs = obs
        self.done_args.append(kwargs)


def test_campaign_overlay_is_dismissed_before_collection(monkeypatch):
    blocked = observation("1", overlays=["forest_campaign"])
    clear = observation("2", [("105g", CROWN)])
    after_tap = observation("3")
    absent = observation("4")
    dismissed = []

    def fake_dismiss(_session, obs):
        dismissed.append(obs.id)
        return clear

    monkeypatch.setattr(recovery, "dismiss", fake_dismiss)
    session = FakeSession(ensure=blocked, stream=[after_tap, absent])

    Forest(session).collect_self()

    assert dismissed == ["1"]
    assert [tap[0] for tap in session.taps] == ["105g"]
    assert session.observe_reasons == ["energy-absence-confirm"]
    assert session.done_obs is absent
    assert session.done_args == [{}]


def test_absence_needs_two_consecutive_bubble_free_observations():
    home = observation("1", [("105g", CROWN)])
    after_first_tap = observation("2")
    reappeared = observation("3", [("25g", CROWN_LOW)])
    after_second_tap = observation("4")
    absent = observation("5")
    session = FakeSession(
        ensure=home, stream=[after_first_tap, reappeared, after_second_tap, absent],
    )

    Forest(session).collect_self()

    assert [tap[0] for tap in session.taps] == ["105g", "25g"]
    assert session.observe_reasons == ["energy-absence-confirm"] * 2
    assert session.done_obs is absent


def test_bubble_tap_without_effect_is_retried_only_three_times():
    home = observation("1", [("105g", CROWN)])
    retry = observation("2", [("105g", CROWN)])
    session = FakeSession(ensure=home, stream=[retry, retry], tap_timeouts=3)

    with pytest.raises(AutomationError, match="Postcondition failed"):
        Forest(session).collect_self()

    assert [tap[0] for tap in session.taps] == ["105g"] * 3
    assert session.observe_reasons == ["collect-energy-retry"] * 2
    assert session.done_args == []


def test_sign_in_bubble_navigation_claims_reward_then_collection_resumes():
    home = observation("1", [("5g", CROWN)])
    reward = observation("2", [("奖励", (400, 300, 900, 400))], page="UNKNOWN")
    reward_waited = observation("3", [("奖励", (400, 300, 900, 400))], page="UNKNOWN")
    claimable = observation("4", [("立即领取", (500, 2400, 900, 2500))], page="UNKNOWN")
    claimed = observation("5", [], page="UNKNOWN")
    back_home = observation("6")
    absent = observation("7")
    session = FakeSession(
        ensure=home,
        stream=[reward, reward_waited, claimable, claimed, back_home, absent],
    )

    Forest(session).collect_self()

    assert [tap[0] for tap in session.taps] == ["5g", "[立三主]即领取"]
    assert session.waits == []
    assert session.observe_reasons == ["energy-sign-reward", "energy-absence-confirm"]
    assert len(session.scrolls) == 1 and session.scrolls[0]["allow_unknown"] is True
    assert len(session.backs) == 1
    assert callable(session.backs[0][0]) and session.backs[0][1] is True
    assert session.done_obs is absent
    assert session.done_args == [{}]


def test_home_lingjiangli_button_never_satisfies_the_sign_destination_wait():
    # Real-device evidence (2026-09-22): a bare "奖励" pattern matched the
    # forest home's "领奖励" button, the reward flow started on the home page
    # and the bounded scroll for "立即领取" timed out.
    home = observation("1", [("126g", CROWN)])
    after_tap = observation("2", [("领奖励", (700, 2100, 900, 2200))], page="treasure")
    still_off_page = observation("3", [("领奖励", (700, 2100, 900, 2200))], page="treasure")
    recovered = observation("4")
    absent = observation("5")
    session = FakeSession(ensure=home, stream=[after_tap, still_off_page, recovered, absent])

    Forest(session).collect_self()

    assert session.waits == []
    assert [tap[0] for tap in session.taps] == ["126g"]
    assert session.scrolls == []
    assert len(session.backs) == 1
    assert callable(session.backs[0][0]) and session.backs[0][1] is True
    assert session.done_obs is absent


def test_sign_label_ocr_variant_excludes_the_ball_and_still_claims():
    # Real-device evidence (2026-09-22): OCR read the label as "能量答到"
    # (答 for 签) and the claim button as "主即领取" (主 for 立); the separate
    # "5g能量" text is the 神奇海洋 reminder pill, not a sign-in reading.
    home = observation("1", [
        ("5g", SIGN_BALL),
        ("能量答到", SIGN_TEXT),
        ("5g能量", (511, 1217, 613, 1266)),
    ])
    absent = observation("2")
    sign_seen = observation("3", [("5g", SIGN_BALL), ("能量答到", SIGN_TEXT)])
    destination = observation("4", [("奖励", (400, 300, 900, 400))], page="UNKNOWN")
    claimable = observation("5", [("主即领取", (500, 2400, 900, 2500))], page="UNKNOWN")
    claimed = observation("6", [], page="UNKNOWN")
    back_home = observation("7")
    session = FakeSession(
        ensure=home,
        stream=[absent, sign_seen, destination, claimable, claimed, back_home],
        config={"energy_sign_wait": 6},
    )

    Forest(session).collect_self()

    assert [tap[0] for tap in session.taps] == ["5g", "[立三主]即领取"]
    assert session.observe_reasons == [
        "energy-absence-confirm", "delayed-energy-sign", "energy-sign-reward",
    ]
    assert session.taps[0][1]["name"] == "energy-sign"
    assert session.taps[1][1]["spend"] is True
    assert session.scrolls == []  # the claim control is exposed on entry
    assert len(session.backs) == 1
    assert callable(session.backs[0][0]) and session.backs[0][1] is True
    assert session.done_obs is back_home
    assert session.done_args == [{}]


def test_park_ball_and_plaza_badges_next_to_labels_are_not_bubbles():
    # Real-device evidence (2026-09-22): the "25g" ball ~150px above the
    # 乐园 label opened the park task panel when tapped, and card badges
    # like "260g" enter the band whenever the home renders scrolled.
    obs = observation("9", [
        ("25g", (81, 1162, 157, 1224)),      # ball over the park entrance
        ("乐园", (110, 1300, 200, 1388)),
        ("260g", (700, 1540, 795, 1620)),     # card badge inside the band
        ("能量雨", (640, 1650, 780, 1700)),
        ("105g", CROWN),
    ])

    assert [bubble.text for bubble in Forest._bubbles(obs)] == ["105g"]


def test_scrolled_entry_is_settled_to_top_before_collection():
    # Real-device evidence (2026-09-22): the entry frame restored the home
    # scrolled down ~.25 - crown bubbles off-screen, the park ball inside
    # the band; the settled frame shows the top layout with real bubbles.
    scrolled = observation("1", [
        ("25g", (81, 1162, 157, 1224)),      # in-band only while scrolled
        ("乐园", (110, 1300, 200, 1388)),
        ("森林广场", (120, 1500, 250, 1585)),  # center (.127, .482): scrolled
    ])
    settled = observation("2", [
        ("森林广场", (120, 2305, 250, 2393)),  # center (.127, .734): top
        ("126g", (300, 616, 397, 716)),
    ])
    after_tap = observation("3")
    absent = observation("4")
    session = FakeSession(
        ensure=scrolled, stream=[settled, after_tap, absent],
    )

    Forest(session).collect_self()

    assert len(session.scrolls) == 1  # only the settle swipe
    assert [tap[0] for tap in session.taps] == ["126g"]
    assert session.done_obs is absent


def test_park_panel_excursion_backs_out_and_reenters_the_forest():
    # Real-device evidence (2026-09-22): tapping the park ball opened the
    # task panel ("完成任务得奖励"), whose heading must not be claimed as a
    # sign reward, and Back overshot to the Alipay home.
    home = observation("1", [("25g", (81, 1162, 157, 1224))])
    panel = observation("2", [
        ("完成任务得奖励", (400, 540, 1040, 620)),
        ("每日签到", (300, 780, 700, 860)),
        ("领取", (1160, 840, 1360, 920)),
    ], page="UNKNOWN")
    scrolled_panel = observation("3", [
        ("完成任务得奖励", (400, 300, 1040, 380)),
        ("领取", (1160, 540, 1360, 620)),
    ], page="UNKNOWN")
    after_scroll = observation("4", [("完成任务得奖励", (400, 300, 1040, 380))],
                               page="UNKNOWN")
    still_panel = observation("5", [("完成任务得奖励", (400, 300, 1040, 380))],
                              page="UNKNOWN")
    overshoot = observation("6", [("蚂蚁森林", (180, 220, 460, 280))], page="alipay")
    reentered = observation("7")
    absent = observation("8")
    session = FakeSession(
        ensure=home,
        stream=[panel, scrolled_panel, after_scroll, still_panel, overshoot, absent],
        reentries=[reentered],
    )

    Forest(session).collect_self()

    assert session.ensure_calls == 2
    assert [tap[0] for tap in session.taps] == ["25g"]
    assert len(session.scrolls) == 1  # the bounded look for 立即领取
    assert len(session.backs) == 1
    assert callable(session.backs[0][0]) and session.backs[0][1] is True
    assert session.observe_reasons == [
        "energy-sign-reward", "energy-sign-reward-absent",
        "energy-absence-confirm",
    ]
    assert session.done_obs is absent
    assert session.done_args == [{}]


def test_friend_detour_page_is_harvested_before_leaving():
    # Real-device evidence (2026-09-23): the crown floater opened
    # 小布的蚂蚁森林 with "一键收" exposed and 119g pending, but the old
    # recovery only backed out - the run harvested no friend energy at all.
    home = observation("1", [("105g", CROWN)])
    friend = observation("2", [
        ("小布的蚂蚁森林", (180, 220, 700, 300)),
        ("TA待收的能量 119g", (180, 1500, 700, 1580)),
        ("一键收", (1050, 2050, 1330, 2160)),
    ], page="forest_friend")
    harvested = observation("3", [
        ("小布的蚂蚁森林", (180, 220, 700, 300)),
    ], page="forest_friend")
    back_home = observation("4")
    absent = observation("5")
    session = FakeSession(ensure=home, stream=[friend, harvested, back_home, absent])

    Forest(session).collect_self()

    assert [tap[0] for tap in session.taps] == ["105g", "一键收"]
    assert len(session.backs) == 1
    assert callable(session.backs[0][0]) and session.backs[0][1] is True
    assert session.done_obs is absent
    assert session.done_args == [{}]


def test_friend_detour_without_one_click_backs_out_without_tapping():
    home = observation("1", [("105g", CROWN)])
    friend = observation("2", [
        ("小布的蚂蚁森林", (180, 220, 700, 300)),
    ], page="forest_friend")
    back_home = observation("3")
    absent = observation("4")
    session = FakeSession(ensure=home, stream=[friend, back_home, absent])

    Forest(session).collect_self()

    assert [tap[0] for tap in session.taps] == ["105g"]
    assert len(session.backs) == 1
    assert session.done_obs is absent


def test_home_misclassified_as_treasure_is_caught_by_the_plaza_anchor():
    # Real-device evidence (2026-09-23): the home strip's persistent
    # "立即抽奖" card plus the flickering 森林寻宝 badge classified the crown
    # band as treasure, the tap stalled, and the recovery backed all the way
    # out to the Alipay home before ensure() re-entered.
    home = observation("1", [("66g", (305, 640, 414, 727))])
    blocked = observation("2", [
        ("森林寻宝", (1200, 680, 1382, 758)),   # floating badge, flickers in
        ("立即抽奖", (600, 2100, 850, 2196)),    # strip card on the home itself
        ("森林广场", (120, 2305, 250, 2393)),    # plaza anchor, home only
        ("66g", (305, 640, 414, 727)),
    ], page="treasure")
    cleared = observation("3")
    absent = observation("4")
    session = FakeSession(
        ensure=home, stream=[blocked, cleared, absent], tap_timeouts=1,
    )

    Forest(session).collect_self()

    assert session.backs == []            # no spurious back-out excursion
    assert [tap[0] for tap in session.taps] == ["66g", "66g"]
    assert session.observe_reasons == ["collect-energy-retry",
                                       "energy-absence-confirm"]
    assert session.done_obs is absent
