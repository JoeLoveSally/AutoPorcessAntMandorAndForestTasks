"""Offline business-state tests; these do not validate real-device selectors."""

import unittest
from types import SimpleNamespace

from domain_data import AutomationError, Element, Observation
from workflow.manor.home import ManorHome


def observation(oid, texts, page="manor"):
    return Observation(oid, 0.0, 1440, 3200, "alipay",
                       [Element(text, (100, 1900, 250, 1980), oid) for text in texts], page=page)


def frame(oid, entries, page="manor"):
    return Observation(oid, 0.0, 1440, 3200, "alipay",
                       [Element(text, bounds, oid) for text, bounds in entries], page=page)


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
        self.entry = None
        self.ex = SimpleNamespace(store=SimpleNamespace(
            verified_status=lambda _task: self.verified))

    def ensure(self, page):
        self.ensure_calls.append(page)
        return self.first

    def observe(self, reason):
        return self.entry if self.entry is not None else self.after

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


class CapturingSession(FakeSession):
    """Exposes the postcondition the reward loop handed to tap_element."""

    def tap_element(self, obs, element, predicate, **kwargs):
        self.predicate = predicate
        return self.after


class StaleRewardSession(FakeSession):
    """The pixel guard refuses the reward tap, so nothing reaches the phone."""

    verify_reasons = ()

    def tap_element(self, obs, element, predicate, **kwargs):
        raise AutomationError("Target changed since observation", "STALE")

    def observe(self, reason):
        self.verify_reasons = self.verify_reasons + (reason,)
        return self.after


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

    def test_reward_postcondition_ignores_the_floating_banner(self):
        # Device evidence (2026-10-09, run a3b524): the 请客吃饭啦 banner
        # floats at y .859, inside the old reward region, so its appearance
        # alone satisfied the text-tuple comparison while the 打赏 card was
        # unchanged - the loop then re-tapped the lingering card and died on
        # the pixel guard's STALE. The comparison now rides the reward row
        # (.754-.786), so only the card's own change counts.
        card = [("茵茵/小时前", (257, 2412, 459, 2456)),
                ("帮你喂食", (260, 2461, 424, 2506)),
                ("打赏", (528, 2470, 601, 2514))]
        banner = [("请客吃饭啦", (565, 2750, 785, 2793))]
        before = frame("1", card)
        still = frame("2", card + banner)
        gone = frame("3", banner)

        session = CapturingSession(before, gone)
        ManorHome(session).reward_friends()
        self.assertFalse(session.predicate(still))
        self.assertTrue(session.predicate(gone))
        self.assertEqual(session.done_args, [{"skipped": False}])

    def test_reward_postcondition_ignores_stamp_jitter_on_the_same_card(self):
        # Device evidence (2026-10-09, run 64f66a): the 小号's third reward
        # left the SAME 健桥 card mid-animation while OCR re-read its stamp
        # 健桥/天前 as 健桥1天前 and shifted the row ~30px - a raw text
        # comparison called the unchanged card a new one, the loop re-tapped
        # it, and the pixel guard's STALE killed the run. Only the CJK runs
        # count, so the jittered stamp still compares equal to the original
        # while a different friend's name still changes the row.
        card = [("健桥/天前", (257, 2414, 419, 2453)),
                ("帮你喂食", (260, 2461, 424, 2506)),
                ("打赏", (491, 2470, 564, 2514))]
        jitter = [("健桥1天前", (228, 2416, 390, 2454)),
                  ("帮你喂食", (231, 2461, 393, 2506)),
                  ("打赏", (461, 2472, 535, 2512))]
        other = [("妙娟/天前", (257, 2414, 419, 2453)),
                 ("帮你喂食", (260, 2461, 424, 2506)),
                 ("打赏", (491, 2470, 564, 2514))]

        session = CapturingSession(frame("1", card), frame("2", []))
        ManorHome(session).reward_friends()
        self.assertFalse(session.predicate(frame("jitter", jitter)))
        self.assertTrue(session.predicate(frame("other", other)))

    def test_stale_reward_tap_is_verified_against_the_fresh_card(self):
        # Device evidence (2026-10-09, run 64f66a): the pixel guard refused
        # the tap (nothing was sent) while the card was mid-animation. The
        # design forbids repeating a submission blind, so the loop must
        # verify the card on a fresh frame - consumed here means the reward
        # landed and the task is SUCCESS, never a failure.
        card = [("健桥/天前", (257, 2414, 419, 2453)),
                ("帮你喂食", (260, 2461, 424, 2506)),
                ("打赏", (491, 2470, 564, 2514))]
        session = StaleRewardSession(frame("1", card), frame("2", []))
        ManorHome(session).reward_friends()
        self.assertIn("reward-friend-verify", session.verify_reasons)
        self.assertEqual(session.done_args, [{"skipped": False}])

    def test_stale_reward_tap_with_the_card_still_there_still_fails(self):
        # A refused tap whose card is still on screen proves nothing landed;
        # the loop must fail closed instead of reporting the reward given.
        card = [("健桥/天前", (257, 2414, 419, 2453)),
                ("帮你喂食", (260, 2461, 424, 2506)),
                ("打赏", (491, 2470, 564, 2514))]
        session = StaleRewardSession(frame("1", card), frame("2", card))
        with self.assertRaises(AutomationError):
            ManorHome(session).reward_friends()
        self.assertEqual(session.done_args, [])

    def test_diary_already_done_does_not_submit_again(self):
        entry = observation("0", ["小鸡日记", "领饲料"], page="manor")
        done = observation("1", ["明日再来"], page="diary")
        session = FakeSession(done, done)
        session.entry = entry
        ManorHome(session).diary()
        self.assertEqual(session.ensure_calls, ["diary"])
        self.assertEqual(session.taps, [])
        self.assertEqual(session.done_args, [{"already": True}])
        self.assertEqual(session.back_calls, [("manor",)])

    def test_diary_requires_verified_completion(self):
        entry = observation("0", ["小鸡日记", "领饲料"], page="manor")
        before = observation("1", ["贴贴小鸡"], page="diary")
        after = observation("2", ["明日再来"], page="diary")
        session = FakeSession(before, after)
        session.entry = entry
        ManorHome(session).diary()
        self.assertEqual(session.ensure_calls, ["diary"])
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

    def test_absent_entry_without_a_record_is_a_terminal_skip(self):
        # Device evidence (2026-10-08/09, runs 133fc5 and 3a6860): an
        # ungenerated diary day renders no anchor at all - OCR and the
        # calibrated red-book vision band both empty on the business
        # day's first attempt, with nothing read earlier and no app
        # update. User directive (2026-10-09) "没有提示就不做": the
        # missing prompt ends this run's diary as a terminal skip and
        # lets the chain continue; it must never abort the run, and the
        # decision needs no routing because the frame is already home.
        manor = observation("1", ["领饲料", "家庭"], page="manor")

        class MissingEntrySession(FakeSession):
            def ensure(self, page):
                self.ensure_calls.append(page)
                raise AssertionError(f"no routing expected, got ensure({page})")

        session = MissingEntrySession(manor, manor)
        session.verified = None
        ManorHome(session).diary()
        self.assertEqual(session.ensure_calls, [])
        self.assertEqual(session.done_args, [{"skipped": True}])
        self.assertEqual(session.taps, [])
        self.assertEqual(session.back_calls, [])

    def test_diary_from_another_page_routes_home_before_deciding(self):
        # decide-on-manor also covers a non-chain entry state: only a
        # home frame without the anchor is the no-prompt skip; any other
        # page routes home first so a stray feed/diary frame cannot fake
        # the absence.
        elsewhere = observation("1", ["饲料任务"], page="feed")
        home = observation("2", ["领饲料", "家庭"], page="manor")
        session = FakeSession(home, elsewhere)
        session.entry = elsewhere
        session.verified = None
        ManorHome(session).diary()
        self.assertEqual(session.ensure_calls, ["manor"])
        self.assertEqual(session.done_args, [{"skipped": True}])
        self.assertEqual(session.taps, [])


if __name__ == "__main__":
    unittest.main()
