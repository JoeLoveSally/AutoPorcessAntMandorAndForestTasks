from types import SimpleNamespace

import pytest

from action_executor import Executor
from domain_data import AutomationError, Element, Observation
from state_machine import Budget
from workflow.recovery import dismiss
from workflow.session import Session


class Observer:
    def __init__(self, observations):
        self.observations = iter(observations)

    def capture(self, _reason):
        return next(self.observations)


def observation(oid, *, page="manor", overlays=None):
    return Observation(oid, 0.0, 1440, 3200, "alipay", [], page, overlays or [])


def test_wait_dismisses_known_interruption_then_continues_postcondition():
    blocked = observation("blocked", overlays=["manor_ad"])
    recovered = observation("recovered")
    executor = Executor(
        SimpleNamespace(),
        Observer([blocked]),
        SimpleNamespace(emit=lambda *_args, **_kwargs: None),
        SimpleNamespace(),
        "alipay",
        Budget(5),
    )
    handled = []

    def recover(obs):
        handled.append(obs.id)
        return recovered

    executor.interruption_handler = recover

    result = executor.wait(lambda obs: obs.id == "recovered", timeout=1)

    assert result is recovered
    assert handled == ["blocked"]


def test_wait_does_not_dismiss_overlay_that_is_itself_completion_evidence():
    reward = observation("reward", page="lottery", overlays=["reward"])
    executor = Executor(
        SimpleNamespace(),
        Observer([reward]),
        SimpleNamespace(emit=lambda *_args, **_kwargs: None),
        SimpleNamespace(),
        "alipay",
        Budget(5),
    )
    executor.interruption_handler = lambda _obs: (_ for _ in ()).throw(AssertionError())

    assert executor.wait(lambda obs: "reward" in obs.overlays, timeout=1) is reward


def test_session_dismisses_known_overlay_before_next_page_action():
    blocked = Observation(
        "blocked", 0.0, 1440, 3200, "alipay",
        [Element("我知道啦", (500, 1800, 900, 1950), "blocked")],
        page="farm", overlays=["reward"],
    )
    clear = Observation(
        "clear", 1.0, 1440, 3200, "alipay",
        [Element("施肥", (500, 2500, 900, 2650), "clear")], page="farm",
    )

    class FakeExecutor:
        def __init__(self):
            observations = iter((blocked, clear))
            self.observer = SimpleNamespace(capture=lambda _reason: next(observations))
            self.budget = SimpleNamespace(check=lambda: None)
            self.store = SimpleNamespace(unresolved=lambda _task: [])
            self.interruption_handler = None
            self.tapped = None

        def tap(self, obs, element, predicate, *_args, **_kwargs):
            if element.text == "施肥":
                self.tapped = (obs.id, element.text)
            assert predicate(clear)
            return clear

    executor = FakeExecutor()
    session = Session(executor, {})
    session.task = "farm"

    session.tap("^施肥$", lambda obs: obs.page == "farm")

    assert executor.tapped == ("clear", "施肥")


def test_guess_overlay_taps_the_handwritten_giveup_button_despite_ocr_confusion():
    # Device evidence (2026-09-23, run 20260923-105105): the handwritten
    # 放弃奖励 OCRs as 教弃奖励 in 5/5 frames (放→教), so an exact match
    # failed dismiss with found 0 - widen the character class like the
    # 立即* family.
    guess = Observation(
        "guess", 0.0, 1440, 3200, "alipay",
        [Element("猜价格赢抽奖机会", (486, 2533, 954, 2591), "guess"),
         Element("教弃奖励", (578, 2751, 851, 2870), "guess")],
        page="ad", overlays=["guess"],
    )
    clear = Observation("clear", 1.0, 1440, 3200, "alipay", [], page="ad")

    class RecordingSession(Session):
        def __init__(self):
            super().__init__(SimpleNamespace(), {})
            self.task = "forest.friends"
            self.tapped = None
            self._captures = iter((clear,))

        def observe(self, _reason="observe"):
            return next(self._captures)

        def tap_element(self, obs, element, predicate, *, name, **_kwargs):
            self.tapped = (name, element.text, element.bounds)
            assert predicate(clear)

    session = RecordingSession()

    result = dismiss(session, guess)

    assert result is clear
    assert session.tapped == ("dismiss-guess", "教弃奖励", (578, 2751, 851, 2870))


def test_guess_overlay_taps_bottom_center_when_ocr_drops_the_line():
    # Same modal with the button line absent from OCR entirely: tap the
    # proven bottom-center position (0.496w, 0.878h from the frame above)
    # and let the overlay-removal postcondition guard the blind tap.
    guess = Observation(
        "guess", 0.0, 1440, 3200, "alipay",
        [Element("猜价格赢抽奖机会", (486, 2533, 954, 2591), "guess")],
        page="ad", overlays=["guess"],
    )
    clear = Observation("clear", 1.0, 1440, 3200, "alipay", [], page="ad")

    class RecordingSession(Session):
        def __init__(self):
            super().__init__(SimpleNamespace(), {})
            self.task = "forest.friends"
            self.tapped = None
            self._captures = iter((clear,))

        def observe(self, _reason="observe"):
            return next(self._captures)

        def scroll(self, *_args, **_kwargs):
            raise AssertionError("the guess modal does not scroll")

        def tap_element(self, obs, element, predicate, *, name, **_kwargs):
            self.tapped = (name, element)
            assert predicate(clear)

    session = RecordingSession()

    result = dismiss(session, guess)

    assert result is clear
    name, element = session.tapped
    assert name == "dismiss-guess"
    assert element.text == "放弃奖励"
    x1, y1, x2, y2 = element.bounds
    assert abs((x1 + x2) / 2 - 0.496 * 1440) <= 1
    assert abs((y1 + y2) / 2 - 0.878 * 3200) <= 1


def test_furniture_promo_closes_via_the_circle_below_the_card():
    # Device evidence (2026-09-25, run 0c01e7): the family promo is a
    # full-screen modal whose bare close circle sits below the card at
    # CTA 去看看 point + (-2,+293) (frame 0004: CTA (720,2372), circle
    # center (718,2665), r~41). Back would leave the family H5 and strand
    # the blocked step on manor, so this branch must tap, never back.
    promo = Observation(
        "promo", 0.0, 1440, 3200, "alipay",
        [Element("欢乐全家桶", (160, 216, 491, 269), "promo"),
         Element("家庭家具上新啦", (270, 554, 1166, 711), "promo"),
         Element("去看看", (633, 2341, 808, 2404), "promo"),
         Element("三即签到", (599, 2950, 851, 3016), "promo")],
        page="family", overlays=["reward"],
    )
    clear = Observation("clear", 1.0, 1440, 3200, "alipay", [], page="family")

    class RecordingSession(Session):
        def __init__(self):
            super().__init__(SimpleNamespace(), {})
            self.task = "manor.family.donate_egg"
            self.tapped = None
            self._captures = iter((clear,))

        def observe(self, _reason="observe"):
            return next(self._captures)

        def tap_element(self, obs, element, predicate, *, name, **_kwargs):
            self.tapped = (name, element)
            assert predicate(clear)

    session = RecordingSession()

    result = dismiss(session, promo)

    assert result is clear
    name, element = session.tapped
    assert name == "dismiss-furniture"
    x1, y1, x2, y2 = element.bounds
    assert abs((x1 + x2) / 2 - 718) <= 1
    assert abs((y1 + y2) / 2 - 2665) <= 1
    assert x2 - x1 == 180 and y2 - y1 == 180


def test_home_promo_closes_via_its_circle_and_never_back():
    # Device evidence (2026-09-25, run 41640d): the 广州生活卡 card over
    # the Alipay home occluded the forest entry icon. Back on the home
    # walks out of the app (the launcher hazard), so this overlay must
    # close through the vision circle only.
    promo = Observation(
        "promo", 0.0, 1440, 3200, "alipay",
        [Element("广州生活卡", (628, 1229, 830, 1277), "promo"),
         Element("广告关闭", (675, 2153, 764, 2243), "promo")],
        page="alipay", overlays=["home_promo"],
    )
    clear = Observation("clear", 1.0, 1440, 3200, "alipay", [], page="alipay")

    class RecordingSession(Session):
        def __init__(self):
            super().__init__(SimpleNamespace(), {})
            self.task = "forest.self"
            self.tapped = None
            self._captures = iter((clear,))
            self.ex = SimpleNamespace(tap=self._tap)

        def _tap(self, _obs, close, predicate, name, _task, **_kwargs):
            assert predicate(clear)
            self.tapped = (name, close)

        def observe(self, _reason="observe"):
            return next(self._captures)

        def back_observation(self, *_args, **_kwargs):
            raise AssertionError("Back on the Alipay home would exit the app")

    session = RecordingSession()

    result = dismiss(session, promo)

    assert result is clear
    name, close = session.tapped
    assert name == "close-home-promo"
    assert close.text == "广告关闭"


def test_farm_promo_closes_via_its_circle_and_never_back():
    # Device evidence (2026-09-26, run 7d8d95): the timed 领3000肥料 card
    # popped over the auto-jump drawer. Back would abandon the farm whose
    # drawer has no static entry, so the card closes through the vision
    # circle only.
    promo = Observation(
        "promo", 0.0, 1440, 3200, "alipay",
        [Element("领3000肥料", (493, 1640, 941, 1722), "promo"),
         Element("广告关闭", (674, 2329, 764, 2419), "promo")],
        page="farm", overlays=["farm_promo"],
    )
    clear = Observation("clear", 1.0, 1440, 3200, "alipay", [], page="farm")

    class RecordingSession(Session):
        def __init__(self):
            super().__init__(SimpleNamespace(), {})
            self.task = "manor.feed.farm"
            self.tapped = None
            self._captures = iter((clear,))
            self.ex = SimpleNamespace(tap=self._tap)

        def _tap(self, _obs, close, predicate, name, _task, **_kwargs):
            assert predicate(clear)
            self.tapped = (name, close)

        def observe(self, _reason="observe"):
            return next(self._captures)

        def back_observation(self, *_args, **_kwargs):
            raise AssertionError("Back would abandon the auto-jump drawer")

    session = RecordingSession()

    result = dismiss(session, promo)

    assert result is clear
    name, close = session.tapped
    assert name == "close-farm-promo"
    assert close.text == "广告关闭"


def test_app_update_prompt_wins_the_close_and_never_back_or_update():
    # Device evidence (2026-10-08, run 1ed031): the 版本更新 prompt dims
    # the home band while the banner copy stays exposed, so its frame can
    # satisfy the home promo scan's gates too - the prompt must win the
    # close (its dismissal undims the band) and press neither Back (walks
    # Alipay out) nor 立即更新 (would start the app update).
    prompt = Observation(
        "prompt", 0.0, 1440, 3200, "alipay",
        [Element("版本更新", (564, 1562, 872, 1640), "prompt"),
         Element("广告关闭", (1123, 1078, 1243, 1198), "prompt")],
        page="alipay", overlays=["app_update", "home_promo"],
    )
    clear = Observation("clear", 1.0, 1440, 3200, "alipay", [], page="alipay")

    class RecordingSession(Session):
        def __init__(self):
            super().__init__(SimpleNamespace(), {})
            self.task = "manor.home.reward_friends"
            self.tapped = None
            self._captures = iter((clear,))
            self.ex = SimpleNamespace(tap=self._tap)

        def _tap(self, _obs, close, predicate, name, _task, **_kwargs):
            assert predicate(clear)
            self.tapped = (name, close)

        def observe(self, _reason="observe"):
            return next(self._captures)

        def back_observation(self, *_args, **_kwargs):
            raise AssertionError("Back on the Alipay home would exit the app")

    session = RecordingSession()

    result = dismiss(session, prompt)

    assert result is clear
    name, close = session.tapped
    assert name == "close-app-update"
    assert close.text == "广告关闭"


def test_furniture_promo_without_its_cta_anchor_fails_closed():
    # The close circle has no OCR text; without the CTA there is nothing
    # to derive its position from, so dismiss must fail visibly instead
    # of falling through to Back (the stranding path observed today).
    promo = Observation(
        "promo", 0.0, 1440, 3200, "alipay",
        [Element("家庭家具上新啦", (270, 554, 1166, 711), "promo")],
        page="family", overlays=["reward"],
    )

    class BareSession(Session):
        def __init__(self):
            super().__init__(SimpleNamespace(), {})
            self.task = "manor.family.donate_egg"

        def observe(self, _reason="observe"):
            raise AssertionError("furniture branch must resolve without re-observing")

        def back_observation(self, *_args, **_kwargs):
            raise AssertionError("Back would leave the family H5")

    with pytest.raises(AutomationError):
        dismiss(BareSession(), promo)
