"""Offline business-state tests; these do not validate real-device selectors."""

import unittest

from domain_data import Element, Observation
from workflow.manor.home import ManorHome, REWARD_REGION


def observation(oid, texts, page="manor"):
    return Observation(oid, 0.0, 1440, 3200, "alipay",
                       [Element(text, (100, 1900, 250, 1980), oid) for text in texts], page=page)


class FakeSession:
    def __init__(self, first, after):
        self.first, self.after = first, after
        self.config = {}
        self.done_args = []
        self.taps = []
        self.back_calls = []

    def ensure(self, page):
        return self.first

    def observe(self, reason):
        return self.after

    def tap_element(self, obs, element, predicate, **kwargs):
        self.taps.append((obs, element, kwargs))
        if not predicate(self.after):
            raise AssertionError("The mocked postcondition did not hold")
        return self.after

    def tap(self, pattern, predicate, **kwargs):
        self.taps.append((pattern, kwargs))
        if not predicate(self.after):
            raise AssertionError("The mocked postcondition did not hold")
        return self.after

    def done(self, obs=None, **kwargs):
        self.done_args.append(kwargs)

    def back(self, pages):
        self.back_calls.append(pages)


class ManorHomeTests(unittest.TestCase):
    def test_absent_reward_is_skipped(self):
        session = FakeSession(observation("1", []), observation("2", []))
        ManorHome(session).reward_friends()
        self.assertEqual(session.done_args, [{"skipped": True}])
        self.assertEqual(session.taps, [])

    def test_rewarded_friend_is_success_not_skipped(self):
        before = observation("1", ["打赏"])
        after = observation("2", [])
        session = FakeSession(before, after)
        ManorHome(session).reward_friends()
        self.assertEqual(len(session.taps), 1)
        self.assertEqual(session.taps[0][2]["spend"], True)
        self.assertEqual(session.done_args, [{"skipped": False}])

    def test_diary_already_done_does_not_submit_again(self):
        done = observation("1", ["明日再来"], page="diary")
        session = FakeSession(done, done)
        ManorHome(session).diary()
        self.assertEqual(session.taps, [])
        self.assertEqual(session.done_args, [{"already": True}])
        self.assertEqual(session.back_calls, [("manor",)])

    def test_diary_requires_verified_completion(self):
        before = observation("1", ["贴贴小鸡"], page="diary")
        after = observation("2", ["明日再来"], page="diary")
        session = FakeSession(before, after)
        ManorHome(session).diary()
        self.assertEqual(len(session.taps), 1)
        self.assertTrue(session.taps[0][1]["spend"])
        self.assertEqual(session.done_args, [{}])
        self.assertEqual(session.back_calls, [("manor",)])


if __name__ == "__main__":
    unittest.main()
