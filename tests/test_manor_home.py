"""Offline business-state tests; these do not validate real-device selectors."""

import unittest
from types import SimpleNamespace

from domain_data import AutomationError, Element, Observation
from workflow.manor.home import ManorHome


def observation(oid, texts, page="manor"):
    return Observation(oid, 0.0, 1440, 3200, "alipay",
                       [Element(text, (100, 1900, 250, 1980), oid) for text in texts], page=page)


class FakeSession:
    def __init__(self, first, after):
        self.first, self.after = first, after
        self.config = {}
        self.task = "manor.home.diary"
        self.done_args = []
        self.taps = []
        self.back_calls = []
        self.ensure_calls = []
        self.verified = None
        self.ex = SimpleNamespace(store=SimpleNamespace(
            verified_status=lambda _task: self.verified))

    def ensure(self, page):
        self.ensure_calls.append(page)
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

    def test_consumed_diary_entry_with_the_days_record_is_already_done(self):
        # Device evidence (2026-09-29, runs 5742c4 -> 97e388): reading the
        # diary removed the red book entry from the manor, so the
        # always-reprobe re-run found no 小鸡日记 anchor across four frames
        # - anchor absent plus the day's page-verified record is the
        # completion evidence, and ensure("diary") must not be attempted.
        manor = observation("1", ["领饲料", "家庭"], page="manor")
        session = FakeSession(manor, manor)
        session.verified = "SUCCESS"
        ManorHome(session).diary()
        self.assertEqual(session.ensure_calls, [])
        self.assertEqual(session.done_args, [{"already": True}])
        self.assertEqual(session.taps, [])
        self.assertEqual(session.back_calls, [])

    def test_consumed_entry_without_a_record_still_fails_the_first_attempt(self):
        # The same probe without the verified record must keep the
        # fail-closed routing: a first attempt missing its entry is a real
        # error, never a silent skip.
        manor = observation("1", ["领饲料", "家庭"], page="manor")

        class MissingEntrySession(FakeSession):
            def ensure(self, page):
                self.ensure_calls.append(page)
                raise AutomationError(
                    "Expected unique target 小鸡日记|^日记$: found 0", "AMBIGUOUS")

        session = MissingEntrySession(manor, manor)
        session.verified = None
        with self.assertRaises(AutomationError):
            ManorHome(session).diary()
        self.assertEqual(session.ensure_calls, ["diary"])
        self.assertEqual(session.done_args, [])
        self.assertEqual(session.taps, [])


if __name__ == "__main__":
    unittest.main()
