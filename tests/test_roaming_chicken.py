"""A text instruction is not a safe click target for a moving chicken."""

import unittest

from domain_data import AutomationError, Observation, Element
from workflow.manor.home import ManorHome


class FakeSession:
    config = {}

    def __init__(self):
        self.home = Observation("home", 0, 1440, 3200, "alipay",
                                [Element("马上去找TA", (600, 1800, 950, 1900), "home")],
                                page="manor")
        self.friend = Observation("friend", 1, 1440, 3200, "alipay",
                                  [Element("带小鸡回家", (500, 2700, 900, 2800), "friend")],
                                  page="manor_friend")
        self.taps = []
        self.captures = []

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


class RoamingChickenTests(unittest.TestCase):
    def test_text_hint_does_not_get_tapped_as_a_chicken(self):
        session = FakeSession()
        with self.assertRaises(AutomationError) as caught:
            ManorHome(session).bring_home()
        self.assertEqual(caught.exception.code, "TARGET_UNKNOWN")
        self.assertEqual(session.taps, ["马上去找"])
        self.assertEqual(session.captures, ["roaming-chicken-target-needs-calibration"])


if __name__ == "__main__":
    unittest.main()
