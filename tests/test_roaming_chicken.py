"""A text instruction is not a safe click target for a moving chicken.

Two arrival variants calibrate the target: the roaming board shows the
pointing-hand cue (vision path, run 0aa57b on 09-20), while the employed
board's arrival (run 130950 on 09-26) carries no hand - there my chicken
is identified by its own label band instead.
"""

import unittest

from domain_data import AutomationError, Element, Observation
from workflow.manor.home import ManorHome


class FakeSession:
    def __init__(self, employed=False, friend_elements=None):
        home_text = "小鸡出去工作啦" if employed else "马上去找TA"
        self.home = Observation("home", 0, 1440, 3200, "alipay",
                                [Element(home_text, (600, 1800, 950, 1900), "home")],
                                page="manor")
        elements = friend_elements if friend_elements is not None else [
            Element("带小鸡回家", (500, 2700, 900, 2800), "friend")]
        self.friend = Observation("friend", 1, 1440, 3200, "alipay",
                                  elements, page="manor_friend")
        self.taps = []
        self.captures = []
        self.target = None
        self.done_calls = []

    def ensure(self, target):
        self.assert_page(target)
        return self.home

    def assert_page(self, target):
        if target != "manor":
            raise AssertionError("Unexpected entry page")

    def tap(self, pattern, predicate, **kwargs):
        self.taps.append(pattern)
        if not predicate(self.friend):
            raise AssertionError("Navigation not verified")
        return self.friend

    def observe(self, reason):
        self.captures.append(reason)
        return self.friend

    def tap_element(self, _obs, target, predicate, **kwargs):
        self.target = target
        after = Observation("home-again", 2, 1440, 3200, "alipay",
                            [Element("蚂蚁庄园", (100, 200, 400, 260), "home-again")],
                            page="manor")
        if not predicate(after):
            raise AssertionError("Bring-home landing not verified")
        self.tap_detail = kwargs.get("detail")
        return after

    def done(self, obs=None, **kwargs):
        self.done_calls.append(kwargs)


GUEST_LABELS = [
    # Real bounds from run 130950: mine 不理鸡 left, the other guest
    # TA好友的小鸡 right - only the suffix separates them.
    Element("不理鸡", (464, 1822, 597, 1879), "friend"),
    Element("TA好友的小鸡", (993, 1824, 1240, 1875), "friend"),
]


class RoamingChickenTests(unittest.TestCase):
    def test_text_hint_does_not_get_tapped_as_a_chicken(self):
        session = FakeSession()
        with self.assertRaises(AutomationError) as caught:
            ManorHome(session).bring_home()
        self.assertEqual(caught.exception.code, "TARGET_UNKNOWN")
        self.assertEqual(session.taps, ["马上去找"])
        self.assertEqual(session.captures, ["roaming-chicken-stable"])

    def test_employed_variant_taps_the_board_then_the_labeled_chicken(self):
        # The employed board has no CTA: tapping the board text jumps to
        # the host manor, and with no pointing hand the label band picks
        # my chicken (label center + 75px = the proven manual tap).
        session = FakeSession(employed=True, friend_elements=GUEST_LABELS)

        ManorHome(session).bring_home()

        self.assertEqual(session.taps, ["小鸡出去工作啦|小鸡外出"])
        self.assertEqual(session.captures, ["roaming-chicken-stable"])
        self.assertEqual(session.target.point, (530, 1925))
        self.assertEqual(session.tap_detail, {"side": "left"})
        self.assertEqual(session.done_calls, [{}])

    def test_employed_arrival_without_own_label_fails_closed(self):
        # Only the other guest's label: no hand cue and no label rule
        # means no safe tap target - fail closed instead of guessing.
        session = FakeSession(employed=True,
                              friend_elements=[GUEST_LABELS[1]])
        with self.assertRaises(AutomationError) as caught:
            ManorHome(session).bring_home()
        self.assertEqual(caught.exception.code, "TARGET_UNKNOWN")
        self.assertEqual(session.taps, ["小鸡出去工作啦|小鸡外出"])


if __name__ == "__main__":
    unittest.main()
