from __future__ import annotations

from datetime import datetime, timezone

import pytest
from conftest import make_observation

from domain_data import (
    ActionResult,
    ActionStatus,
    Bounds,
    DetectedScreen,
    Element,
    Overlay,
    OverlayType,
    Page,
    RunResult,
    StepStatus,
)
from runtime.errors import AutomationError, StepTimeout
from workflow.recovery import RecoveryPolicy
from workflow.session import WorkflowSession

# --- helpers ---------------------------------------------------------------


def _observation():
    return make_observation("<?xml version='1.0'?><hierarchy rotation='0' />")


def _screen(
    page: Page,
    overlays: tuple[Overlay, ...] = (),
    elements: tuple[str, ...] = (),
) -> DetectedScreen:
    bound = {key: Element(key, Bounds(0, 0, 10, 10), "obs-1") for key in elements}
    return DetectedScreen(page, _observation(), bound, overlays, ("test",), 0.9)


def _overlay(otype: OverlayType, *keys: str) -> Overlay:
    elements = {key: Element(key, Bounds(0, 0, 10, 10), "obs-1") for key in keys}
    return Overlay(otype, elements, ("marker",), 0.9)


class _Runtime:
    def __init__(self, *, max_attempts: int = 2, settle: float = 0.0):
        self.max_recovery_attempts = max_attempts
        self.settle_seconds = settle


class _Config:
    def __init__(self, runtime: _Runtime):
        self.runtime = runtime


class _Logger:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def emit(self, name: str, **kwargs):
        self.events.append((name, kwargs))


class FakeSession:
    """Minimal stand-in for the parts of WorkflowSession that RecoveryPolicy uses."""

    def __init__(self, observe_seq, tap_after=None, back_after=None, max_attempts=2):
        self.config = _Config(_Runtime(max_attempts=max_attempts))
        self.logger = _Logger()
        self._observe_seq = list(observe_seq)
        self._tap_after = tap_after or {}
        self._back_after = back_after
        self.taps: list[str] = []
        self.backs: list[str] = []

    def observe(self, reason: str) -> DetectedScreen:
        return self._observe_seq.pop(0)

    def _tap_raw(self, screen, key, name, *args, **kwargs):
        self.taps.append(key)
        return None, self._tap_after.get(key)

    def back(self, screen, name):
        self.backs.append(name)
        if self._back_after is None:
            raise AutomationError("back not configured")
        return self._back_after


# --- RecoveryPolicy unit tests --------------------------------------------


def test_recover_dismisses_product_quiz_overlay_then_returns():
    feed = _screen(Page.MANOR_FEED_TASKS)
    popup = _screen(Page.MANOR_FEED_TASKS, (_overlay(OverlayType.PRODUCT_QUIZ, "abandon_reward"),))
    session = FakeSession(
        observe_seq=[popup],
        tap_after={"abandon_reward": feed},
    )
    policy = RecoveryPolicy(session)

    result = policy.recover(popup, (Page.MANOR_FEED_TASKS,))

    assert result.page is Page.MANOR_FEED_TASKS
    assert session.taps == ["abandon_reward"]


def test_recover_dismisses_canvas_promo_overlay_via_close():
    home = _screen(Page.FOREST_HOME)
    covered = _screen(Page.FOREST_HOME, (_overlay(OverlayType.PROMO, "close"),))
    session = FakeSession(
        observe_seq=[covered],
        tap_after={"close": home},
    )
    policy = RecoveryPolicy(session)

    result = policy.recover(covered, (Page.FOREST_HOME,))

    assert result.page is Page.FOREST_HOME
    assert session.taps == ["close"]


def test_recover_closes_promo_before_backing_out():
    home = _screen(Page.FOREST_HOME)
    covered = _screen(Page.FOREST_HOME, (_overlay(OverlayType.PROMO, "close"),))
    session = FakeSession(
        observe_seq=[covered],
        tap_after={"close": home},
    )
    policy = RecoveryPolicy(session)

    result = policy.recover(covered, (Page.FOREST_HOME,))

    assert result.page is Page.FOREST_HOME
    assert session.backs == []
    assert session.taps == ["close"]


def test_recover_backs_out_of_wrong_known_page():
    wrong = _screen(Page.FOREST_HOME)
    feed = _screen(Page.MANOR_FEED_TASKS)
    session = FakeSession(observe_seq=[wrong], back_after=feed)
    policy = RecoveryPolicy(session)

    result = policy.recover(wrong, (Page.MANOR_FEED_TASKS,))

    assert result.page is Page.MANOR_FEED_TASKS
    assert session.backs == ["recovery-back-1"]


def test_recover_exhausts_budget_and_raises():
    wrong = _screen(Page.FOREST_HOME)
    session = FakeSession(
        observe_seq=[wrong, wrong],
        back_after=wrong,
        max_attempts=2,
    )
    policy = RecoveryPolicy(session)

    with pytest.raises(AutomationError, match="Recovery budget exhausted"):
        policy.recover(wrong, (Page.MANOR_FEED_TASKS,))

    assert session.backs == ["recovery-back-1", "recovery-back-2"]


def test_recover_uses_reenter_to_return_to_allowed_page():
    wrong = _screen(Page.FOREST_HOME)
    feed = _screen(Page.MANOR_FEED_TASKS)
    session = FakeSession(observe_seq=[wrong], back_after=None)
    policy = RecoveryPolicy(session)
    calls = []

    def reenter():
        calls.append("reenter")
        return feed

    result = policy.recover(wrong, (Page.MANOR_FEED_TASKS,), reenter=reenter)

    assert result.page is Page.MANOR_FEED_TASKS
    assert calls == ["reenter"]


# --- tap recovery wrapper --------------------------------------------------


class FakeActions:
    def __init__(self, returns):
        self._returns = list(returns)
        self.calls = []

    def execute(self, screen, action, expected, postcondition=None, observe_after=True):
        self.calls.append(action.name)
        return self._returns.pop(0)


class FakeRecovery:
    def __init__(self, screen):
        self.screen = screen
        self.called = False
        self.allowed = None

    def recover(self, screen, allowed_pages, reenter=None):
        self.called = True
        self.allowed = allowed_pages
        return self.screen


def _session_for_tap(initial, actions, recovery):
    session = object.__new__(WorkflowSession)
    session.result = RunResult(
        "run-1", "daily", StepStatus.IN_PROGRESS, datetime.now(timezone.utc)
    )
    session._recovering = False
    session.current = initial
    session.actions = actions
    session.recovery = recovery
    return session


def _result(status, *, point=None, after=None, error="missing"):
    result = ActionResult(
        "x",
        status,
        "obs-1",
        after_observation_id=after.observation.id if after else None,
        point=point,
        error=error,
    )
    return result, after


def test_tap_recovers_source_page_before_retrying_destination_action():
    initial = _screen(Page.MANOR_HOME)
    recovered = _screen(Page.MANOR_HOME)
    target = _screen(Page.MANOR_DIARY)
    actions = FakeActions([
        _result(ActionStatus.REJECTED, point=None),
        _result(ActionStatus.EXECUTED, point=(1, 1), after=target),
    ])
    recovery = FakeRecovery(recovered)
    session = _session_for_tap(initial, actions, recovery)

    out = session.tap(initial, "diary", "open-diary", expected=(Page.MANOR_DIARY,))

    assert out is target
    assert recovery.called and recovery.allowed == (Page.MANOR_HOME,)
    assert actions.calls == ["open-diary", "open-diary"]
    assert session.current is target


def test_tap_does_not_retry_when_point_already_sent():
    initial = _screen(Page.MANOR_DONATION_CONFIRM)
    wrong = _screen(Page.CHICKEN_KITCHEN)
    success = _screen(Page.MANOR_DONATION_SUCCESS)
    actions = FakeActions([
        _result(ActionStatus.REJECTED, point=(100, 100)),
        _result(ActionStatus.EXECUTED, point=None, after=success),
    ])
    recovery = FakeRecovery(_screen(Page.MANOR_DONATION_CONFIRM))
    session = _session_for_tap(initial, actions, recovery)
    session.observe = lambda _reason: wrong

    result = session.tap(
        initial,
        "confirm_donation",
        "donate",
        expected=(Page.MANOR_DONATION_SUCCESS,),
        irreversible=True,
    )

    assert result is success
    # A point was already sent to the device — only Back is allowed; the
    # donation tap itself is never repeated.
    assert not recovery.called
    assert actions.calls == ["donate", "donate-back-out"]


def test_irreversible_sent_tap_stops_when_back_returns_to_source():
    initial = _screen(Page.MANOR_DONATION_CONFIRM, elements=("confirm_donation",))
    wrong = _screen(Page.CHICKEN_KITCHEN)
    restored = _screen(Page.MANOR_DONATION_CONFIRM, elements=("confirm_donation",))
    actions = FakeActions([
        _result(ActionStatus.REJECTED, point=(100, 100)),
        _result(ActionStatus.EXECUTED, point=None, after=restored),
    ])
    session = _session_for_tap(initial, actions, FakeRecovery(initial))
    session.observe = lambda _reason: wrong

    with pytest.raises(AutomationError):
        session.tap(
            initial,
            "confirm_donation",
            "donate",
            expected=(Page.MANOR_DONATION_SUCCESS,),
            irreversible=True,
        )

    assert actions.calls == ["donate", "donate-back-out"]


def test_sent_tap_accepts_late_arriving_expected_page():
    initial = _screen(Page.MANOR_HOME)
    arrived = _screen(Page.MANOR_DIARY)
    session = _session_for_tap(
        initial,
        FakeActions([_result(ActionStatus.REJECTED, point=(10, 10))]),
        FakeRecovery(initial),
    )
    session.observe = lambda reason: arrived

    out = session.tap(initial, "diary", "open-diary", expected=(Page.MANOR_DIARY,))

    assert out is arrived
    assert session.current is arrived


def test_sent_tap_retries_when_source_page_is_unchanged():
    initial = _screen(Page.MANOR_HOME)
    unchanged = _screen(Page.MANOR_HOME, elements=("diary",))
    target = _screen(Page.MANOR_DIARY)
    actions = FakeActions([
        _result(ActionStatus.REJECTED, point=(10, 10)),
        _result(ActionStatus.EXECUTED, point=(10, 10), after=target),
    ])
    session = _session_for_tap(
        initial, actions, FakeRecovery(initial)
    )
    session.observe = lambda reason: unchanged

    out = session.tap(initial, "diary", "open-diary", expected=(Page.MANOR_DIARY,))

    assert out is target
    # Swallowed by a scrim: the source page and element are untouched, so the
    # retry fires without a Back.
    assert actions.calls == ["open-diary", "open-diary"]


def test_sent_tap_backs_out_of_wrong_page_then_retries():
    initial = _screen(Page.ALIPAY_HOME, elements=("forest",))
    wrong = _screen(Page.MANOR_HOME)
    restored = _screen(Page.ALIPAY_HOME, elements=("forest",))
    target = _screen(Page.FOREST_HOME)
    actions = FakeActions([
        _result(ActionStatus.REJECTED, point=(10, 10)),
        _result(ActionStatus.EXECUTED, point=None, after=restored),  # back-out
        _result(ActionStatus.EXECUTED, point=(10, 10), after=target),  # retry
    ])
    session = _session_for_tap(initial, actions, FakeRecovery(initial))

    def observe(reason):
        return wrong if reason.endswith("sent-check") else restored

    session.observe = observe

    out = session.tap(initial, "forest", "forest-open", expected=(Page.FOREST_HOME,))

    assert out is target
    assert actions.calls == ["forest-open", "forest-open-back-out", "forest-open"]


def test_sent_tap_raises_when_back_does_not_restore_source():
    initial = _screen(Page.ALIPAY_HOME, elements=("forest",))
    wrong = _screen(Page.MANOR_HOME)
    actions = FakeActions([
        _result(ActionStatus.REJECTED, point=(10, 10)),
        _result(ActionStatus.EXECUTED, point=None, after=wrong),  # back-out stuck
    ])
    session = _session_for_tap(initial, actions, FakeRecovery(initial))
    session.observe = lambda reason: wrong

    with pytest.raises(AutomationError):
        session.tap(initial, "forest", "forest-open", expected=(Page.FOREST_HOME,))

    assert actions.calls == ["forest-open", "forest-open-back-out"]


def test_tap_does_not_recover_without_expected_pages():
    initial = _screen(Page.MANOR_HOME)
    actions = FakeActions([_result(ActionStatus.REJECTED, point=None)])
    recovery = FakeRecovery(_screen(Page.MANOR_HOME))
    session = _session_for_tap(initial, actions, recovery)

    with pytest.raises(AutomationError):
        session.tap(initial, "reward_friend", "reward")

    assert not recovery.called
    assert actions.calls == ["reward"]


def test_tap_raises_when_recovery_retry_also_fails():
    initial = _screen(Page.MANOR_HOME)
    recovered = _screen(Page.MANOR_HOME)
    actions = FakeActions([
        _result(ActionStatus.REJECTED, point=None),
        _result(ActionStatus.REJECTED, point=None),
    ])
    recovery = FakeRecovery(recovered)
    session = _session_for_tap(initial, actions, recovery)

    with pytest.raises(AutomationError):
        session.tap(initial, "diary", "open-diary", expected=(Page.MANOR_DIARY,))

    assert recovery.called
    assert actions.calls == ["open-diary", "open-diary"]


# --- wait_for recovery -----------------------------------------------------


class _WaitRuntime:
    def __init__(self):
        # Small but positive so the wait loop runs at least once and produces a
        # non-None ``latest`` for the recovery branch to act on.
        self.page_timeout_seconds = 0.01
        self.poll_interval_seconds = 0.01
        self.max_recovery_attempts = 2
        self.settle_seconds = 0.0


class _WaitConfig:
    def __init__(self):
        self.runtime = _WaitRuntime()


def _session_for_wait(observe, recovery):
    session = object.__new__(WorkflowSession)
    session.config = _WaitConfig()
    session.logger = _Logger()
    session.current = _screen(Page.UNKNOWN)
    session.recovery = recovery
    session.observe = observe
    return session


def test_wait_for_recovers_after_timeout():
    unknown = _screen(Page.UNKNOWN)
    home = _screen(Page.MANOR_HOME)
    recovery = FakeRecovery(home)

    def observe(reason):
        return unknown

    session = _session_for_wait(observe, recovery)

    out = session.wait_for(Page.MANOR_HOME, "wait")

    assert out is home
    assert recovery.allowed == (Page.MANOR_HOME,)


def test_wait_for_raises_step_timeout_when_required_element_missing_after_recovery():
    home_without_element = _screen(Page.MANOR_HOME)
    recovery = FakeRecovery(home_without_element)

    def observe(reason):
        return _screen(Page.UNKNOWN)

    session = _session_for_wait(observe, recovery)

    with pytest.raises(StepTimeout):
        session.wait_for(Page.MANOR_HOME, "wait", required=("missing_key",))

    assert recovery.called


def test_wait_for_propagates_recovery_budget_exhaustion():
    recovery = FakeRecovery(_screen(Page.MANOR_HOME))

    def _raising(screen, allowed_pages, reenter=None):
        raise AutomationError("Recovery budget exhausted; latest=unknown")

    recovery.recover = _raising

    def observe(reason):
        return _screen(Page.UNKNOWN)

    session = _session_for_wait(observe, recovery)

    with pytest.raises(AutomationError, match="Recovery budget exhausted"):
        session.wait_for(Page.MANOR_HOME, "wait")


def test_wait_for_requires_two_agreeing_observations():
    unknown = _screen(Page.UNKNOWN)
    home_first = _screen(Page.MANOR_HOME)
    home_second = _screen(Page.MANOR_HOME)
    sequence = [unknown, home_first, home_second]
    recovery = FakeRecovery(home_second)

    def observe(reason):
        return sequence.pop(0)

    session = _session_for_wait(observe, recovery)
    session.config.runtime.page_timeout_seconds = 2.0

    out = session.wait_for(Page.MANOR_HOME, "wait")
    assert out is home_second
    assert not sequence


def test_wait_for_keeps_polling_when_confirmation_disagrees():
    home = _screen(Page.MANOR_HOME)
    sequence = [home, _screen(Page.UNKNOWN), home, _screen(Page.MANOR_HOME)]
    recovery = FakeRecovery(home)

    def observe(reason):
        return sequence.pop(0)

    session = _session_for_wait(observe, recovery)
    session.config.runtime.page_timeout_seconds = 2.0

    out = session.wait_for(Page.MANOR_HOME, "wait")
    assert out.page is Page.MANOR_HOME
    assert not sequence


def test_recover_backs_out_of_unknown_pages():
    feed = _screen(Page.MANOR_FEED_TASKS)
    unknown = _screen(Page.UNKNOWN)
    session = FakeSession(
        observe_seq=[unknown, feed],
        back_after=feed,
    )
    policy = RecoveryPolicy(session)

    result = policy.recover(unknown, (Page.MANOR_FEED_TASKS,))

    assert result.page is Page.MANOR_FEED_TASKS
    assert session.backs == ["recovery-back-1"]


def test_sent_tap_returns_restored_expected_page_when_target_moved():
    # Tapping an energy bubble can open an activity page; Back restores the
    # home but the floating bubble has drifted, so there is nothing to re-tap.
    initial = _screen(Page.FOREST_HOME, elements=("energy_0",))
    campaign = _screen(Page.UNKNOWN)
    restored = _screen(Page.FOREST_HOME)
    actions = FakeActions([
        _result(ActionStatus.REJECTED, point=(10, 10)),
        _result(ActionStatus.EXECUTED, point=None, after=restored),  # back-out
    ])
    session = _session_for_tap(initial, actions, FakeRecovery(initial))
    session.observe = lambda reason: campaign

    out = session.tap(initial, "energy_0", "forest-own-energy-1", expected=(Page.FOREST_HOME,))

    assert out is restored
    assert session.current is restored
    assert actions.calls == ["forest-own-energy-1", "forest-own-energy-1-back-out"]
